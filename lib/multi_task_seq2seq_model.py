""" a seq2seq model """

from copy import deepcopy

import tensorflow as tf
import tensorflow.contrib.seq2seq as seq2seq
from tensorflow.contrib.seq2seq.python.ops import attention_wrapper
from tensorflow.python.layers.core import Dense, dense

from lib.utils import read_num_of_lines

__all__ = ['Multi_Task_Sea2Seq']

class Multi_Task_Seq2Seq():
    """ a multi-task seq2seq model """

    def __init__(self, para):
        self.para = para
        self.dtype = tf.float32
        self.global_step = tf.Variable(0, trainable=False, name='global_step')

        if self.para.mode =='train':
            print('build training graph')
            with tf.name_scope('train'):
                self.set_input()
                self.build_playlist_encoder()
                self.build_seed_song_encoder()
                self.build_concat_layer()
                self.build_decoder()
                self.build_optimizer()

        elif self.para.mode == 'valid':
            print('build validation graph')
            with tf.name_scope('valid'):
                self.set_input()
                self.build_playlist_encoder()
                self.build_seed_song_encoder()
                self.build_concat_layer()
                self.build_decoder()

        elif self.para.mode == 'test':
            print('build testing graph')
            with tf.name_scope('test'):
                self.set_input()
                self.build_playlist_encoder()
                self.build_seed_song_encoder()
                self.build_concat_layer()
                self.build_decoder()

        self.saver = tf.train.Saver(max_to_keep=2)

    def set_input(self):
        """
            This funciton contructs all input data for all modes.

            encoder_inputs: [batch_size, max_len]
            encoder_inputs: [batch_size]
            seed_song_inpuds: [batch_size]
            decoder_inputs: [batch_size, max_len]
            decoder_inputs_len: [batch_size]
            decoder_targets: [batch_size, max_len]
        """

        print('set input nodes...')
        if self.para.mode == 'train' or self.para.mode == 'valid':
            self.raw_encoder_inputs, self.raw_encoder_inputs_len, \
            self.raw_decoder_inputs, self.raw_decoder_inputs_len, \
            self.raw_seed_song_inputs = self.read_batch_sequences(self.para.mode)

            self.encoder_inputs = self.raw_encoder_inputs[:, 1:]
            self.encoder_inputs_len = self.raw_encoder_inputs_len
            self.seed_song_inputs = self.raw_seed_song_inputs
            self.decoder_inputs = self.raw_decoder_inputs[:, :-1]
            self.decoder_inputs_len = self.raw_decoder_inputs_len
            self.decoder_targets = self.raw_decoder_inputs[:, 1:]

            self.predict_count = tf.reduce_sum(self.decoder_inputs_len)

        elif self.para.mode == 'test':
            self.encoder_inputs = tf.placeholder(
                dtype=tf.int32,
                shape=(None, self.para.max_len),
            )
            self.encoder_inputs_len = tf.placeholder(
                dtype=tf.int32,
                shape=(None,)
            )
            self.seed_song_inputs = tf.placeholder(
                dtype=tf.int64,
                shape=(None,)
            )

    def build_playlist_encoder(self):
        print('build playlist encoder...')
        with tf.variable_scope('playlist_encoder'):
            self.encoder_cell = self.build_encoder_cell()

            self.encoder_embedding = tf.get_variable(
                name='embedding',
                shape=[self.para.encoder_vocab_size, self.para.embedding_size],
                dtype=self.dtype
            )
            self.encoder_inputs_embedded = tf.nn.embedding_lookup(
                params=self.encoder_embedding,
                ids=self.encoder_inputs
            )
            self.encoder_outputs, self.encoder_states = tf.nn.dynamic_rnn(
                cell=self.encoder_cell,
                inputs=self.encoder_inputs_embedded,
                sequence_length=self.encoder_inputs_len,
                dtype=self.dtype,
            )

    def build_seed_song_encoder(self):
        print('build seed song encoder...')
        with tf.variable_scope('seed_song_encoder'):
            # self.seed_song_one_hot: [batch_size, encoder_vocab_size]
            self.seed_song_one_hot = tf.one_hot(
                indices=self.seed_song_inputs,
                depth=self.para.encoder_vocab_size
            )
            # self.seed_song_projected: [batch_size, embedding_size]
            self.seed_song_projected = dense(
                inputs=self.seed_song_one_hot,
                units=self.para.embedding_size,
                name='seed_song_projection'
            )
            # use embedding from the encoder
            self.seed_song_embedded = tf.nn.embedding_lookup(
                params=self.encoder_embedding,
                ids=self.seed_song_inputs
            )

    def build_concat_layer(self):
        # self.seed_song_projected_tiled: [batch_size * max_len, embedding_size]
        self.seed_song_projected_tiled = seq2seq.tile_batch(
            self.seed_song_embedded,
            multiplier=self.para.max_len
        )
        # self.seed_song_projected_tiled: [batch_size, max_len, embedding_size]
        self.seed_song_projected_tiled = tf.reshape(
            self.seed_song_projected_tiled,
            [self.para.batch_size, self.para.max_len, self.para.embedding_size]
        )
        # self.concat_encoder_outputs:
        # [batch_size, max_len, num_units + embedding_size]
        self.encoder_outputs_concated = tf.concat(
            values=[self.encoder_outputs, self.seed_song_projected_tiled],
            axis=2,
        )
        # self.encoder_outputs_concated_projected:
        # [batch_size, max_len, num_units]
        self.encoder_outputs_concated_projected = dense(
           inputs=self.encoder_outputs_concated,
           units=self.para.num_units,
           name='concat_projection'
        )

    def build_decoder(self):
        print('build decoder...')
        with tf.variable_scope('decoder'):
            self.decoder_cell, self.decoder_initial_state = \
                self.build_decoder_cell()

            self.decoder_embedding = tf.get_variable(
                name='embedding',
                shape=[self.para.decoder_vocab_size, self.para.embedding_size],
                dtype=self.dtype
            )
            output_projection_layer = Dense(
               units=self.para.decoder_vocab_size,
               name='output_projection'
            )

            if self.para.mode == 'train':
                self.decoder_inputs_embedded = tf.nn.embedding_lookup(
                    params=self.decoder_embedding,
                    ids=self.decoder_inputs
                )

                if self.para.scheduled_sampling == 0:
                    training_helper = seq2seq.TrainingHelper(
                        inputs=self.decoder_inputs_embedded,
                        sequence_length=self.decoder_inputs_len,
                        name='training_helper'
                    )
                else:
                    self.sampling_probability = tf.cond(
                        self.global_step < self.para.start_decay_step * 2,
                        lambda: tf.cast(
                            tf.divide(self.global_step,
                                      self.para.start_decay_step * 2),
                            dtype=self.dtype),
                        lambda: tf.constant(1.0, dtype=self.dtype),
                        name='sampling_probability'
                    )
                    training_helper = seq2seq.ScheduledEmbeddingTrainingHelper(
                        inputs=self.decoder_inputs_embedded,
                        sequence_length=self.decoder_inputs_len,
                        embedding=self.decoder_embedding,
                        sampling_probability=self.sampling_probability,
                        name='training_helper'
                    )

                training_decoder = seq2seq.BasicDecoder(
                    cell=self.decoder_cell,
                    helper=training_helper,
                    initial_state=self.decoder_initial_state,
                    output_layer=output_projection_layer
                )
                max_decoder_length = tf.reduce_max(self.decoder_inputs_len)
                self.decoder_outputs, decoder_states, decoder_outputs_len = \
                    seq2seq.dynamic_decode(
                        decoder=training_decoder,
                        maximum_iterations=max_decoder_length
                    )

                rnn_output = self.decoder_outputs.rnn_output
                # rnn_output should be padded to max_len
                # calculation of loss will be handled by masks
                self.rnn_output_padded = tf.pad(rnn_output, \
                    [[0, 0],
                     [0, self.para.max_len - tf.shape(rnn_output)[1]],
                     [0, 0]] \
                )
                self.loss = self.compute_loss(
                    logits=self.rnn_output_padded,
                    labels=self.decoder_targets
                )

            elif self.para.mode == 'test':
                start_tokens = tf.fill([self.para.batch_size], 1)

                if self.para.beam_search == 0:
                    inference_helper = seq2seq.GreedyEmbeddingHelper(
                        start_tokens=start_tokens,
                        end_token=2,
                        embedding=self.decoder_embedding
                    )
                    inference_decoder = seq2seq.BasicDecoder(
                        cell=self.decoder_cell,
                        helper=inference_helper,
                        initial_state=self.decoder_initial_state,
                        output_layer=output_projection_layer
                    )
                else:
                    inference_decoder = seq2seq.BeamSearchDecoder(
                        cell=self.decoder_cell,
                        embedding=self.decoder_embedding,
                        start_tokens=start_tokens,
                        end_token=2,
                        initial_state=self.decoder_initial_state,
                        beam_width=self.para.beam_width,
                        output_layer=output_projection_layer
                    )

                self.decoder_outputs, decoder_states, decoder_outputs_len = \
                    seq2seq.dynamic_decode(
                        decoder=inference_decoder,
                        maximum_iterations=self.para.max_len
                    )
                if self.para.beam_search == 0:
                    # self.decoder_predictions_id: [batch_size, max_len, 1]
                    self.decoder_predicted_ids = tf.expand_dims( \
                        input=self.decoder_outputs.sample_id, \
                        axis=-1 \
                    )
                else:
                    # self.decoder_predicted_ids: [batch_size, <= max_len, beam_width]
                    self.decoder_predicted_ids = self.decoder_outputs.predicted_ids


    def build_optimizer(self):
        print('build optimizer...')
        trainable_variables = tf.trainable_variables()
        self.learning_rate = tf.cond(
           self.global_step < self.para.start_decay_step,
           lambda: tf.constant(self.para.learning_rate),
           lambda: tf.train.exponential_decay(
               self.para.learning_rate,
               (self.global_step - self.para.start_decay_step),
               self.para.decay_steps,
               self.para.decay_factor,
               staircase=True),
           name="learning_rate"
        )
        self.opt = tf.train.GradientDescentOptimizer(self.learning_rate)
        gradients = tf.gradients(self.loss, trainable_variables)
        clip_gradients, _ = tf.clip_by_global_norm(gradients, \
                                                   self.para.max_gradient_norm)
        self.update = self.opt.apply_gradients(
            zip(clip_gradients, trainable_variables),
            global_step=self.global_step
        )

    def compute_loss(self, logits, labels):
        """
            logits: [batch_size, max_len, decoder_vocab_size]
            labels: [batch_size, max_len]
        """
        crossent = tf.nn.sparse_softmax_cross_entropy_with_logits(
            labels=labels,
            logits=logits
        )
        self.masks = tf.sequence_mask(
            lengths=self.decoder_inputs_len,
            maxlen=self.para.max_len,
            dtype=self.dtype,
            name='masks'
        )
        loss = tf.reduce_sum(crossent * self.masks) / \
               tf.to_float(self.para.batch_size)
        return loss

    def build_encoder_cell(self):
        return tf.contrib.rnn.MultiRNNCell([self.build_single_cell()] * \
                                           self.para.num_layers)
    def build_decoder_cell(self):
        self.decoder_cell_list = \
           [self.build_single_cell() for i in range(self.para.num_layers)]

        if self.para.mode == 'train':
            encoder_outputs = self.encoder_outputs_concated_projected
            encoder_inputs_len = self.encoder_inputs_len
            encoder_states = self.encoder_states
            batch_size = self.para.batch_size
        else:
            encoder_outputs = seq2seq.tile_batch(
                self.encoder_outputs_concated_projected,
                multiplier=self.para.beam_width
            )
            encoder_inputs_len = seq2seq.tile_batch(
                self.encoder_inputs_len,
                multiplier=self.para.beam_width
            )
            encoder_states = seq2seq.tile_batch(
                self.encoder_states,
                multiplier=self.para.beam_width
            )
            batch_size = self.para.batch_size * self.para.beam_width

        if self.para.attention_mode == 'luong':
            # scaled luong: recommended by authors of NMT
            self.attention_mechanism = attention_wrapper.LuongAttention(
                num_units=self.para.num_units,
                memory=encoder_outputs,
                memory_sequence_length=encoder_inputs_len,
                scale=True
            )
            output_attention = True
        else:
            self.attention_mechanism = attention_wrapper.BahdanauAttention(
                num_units=self.para.num_units,
                memory=encoder_outputs,
                memory_sequence_length=encoder_inputs_len
            )
            output_attention = False

        cell = tf.contrib.rnn.MultiRNNCell(self.decoder_cell_list)
        cell = attention_wrapper.AttentionWrapper(
            cell=cell,
            attention_mechanism=self.attention_mechanism,
            attention_layer_size=self.para.num_units,
            name='attention'
        )
        decoder_initial_state = cell.zero_state(batch_size, self.dtype).clone(
            cell_state=encoder_states
        )

        return cell, decoder_initial_state

    def build_single_cell(self):
        cell = tf.contrib.rnn.LSTMCell(self.para.num_units)
        cell = tf.contrib.rnn.DropoutWrapper(
            cell=cell,
            input_keep_prob=(1.0 - self.para.dropout)
        )
        return cell

    def read_batch_sequences(self, mode):
        """ read a batch from .tfrecords """

        file_queue = tf.train.string_input_producer(
            ['./data/rnn_{}.tfrecords'.format(mode)]
        )

        ei, ei_len, di, di_len, sid = self.read_one_sequence(file_queue)

        min_after_dequeue = 3000
        capacity = min_after_dequeue + 3 * self.para.batch_size

        encoder_inputs, encoder_inputs_len, decoder_inputs, decoder_inputs_len, \
        seed_ids = tf.train.shuffle_batch(
            [ei, ei_len, di, di_len, sid],
            batch_size=self.para.batch_size,
            capacity=capacity,
            min_after_dequeue=min_after_dequeue
        )
        encoder_inputs = tf.sparse_tensor_to_dense(encoder_inputs)
        decoder_inputs = tf.sparse_tensor_to_dense(decoder_inputs)

        encoder_inputs_len = tf.reshape(encoder_inputs_len,
                                        [self.para.batch_size])
        decoder_inputs_len = tf.reshape(decoder_inputs_len,
                                        [self.para.batch_size])
        return encoder_inputs, tf.to_int32(encoder_inputs_len), \
               decoder_inputs, tf.to_int32(decoder_inputs_len), seed_ids

    def read_one_sequence(self, file_queue):
        """ read one sequence from .tfrecords"""

        reader = tf.TFRecordReader()

        _, serialized_example = reader.read(file_queue)

        feature = tf.parse_single_example(serialized_example, features={
            'encoder_input': tf.VarLenFeature(tf.int64),
            'encoder_input_len': tf.FixedLenFeature([1], tf.int64),
            'decoder_input': tf.VarLenFeature(tf.int64),
            'decoder_input_len': tf.FixedLenFeature([1], tf.int64),
            'seed_ids': tf.FixedLenFeature([1], tf.int64)
        })

        return feature['encoder_input'], feature['encoder_input_len'], \
               feature['decoder_input'], feature['decoder_input_len'], \
               feature['seed_ids']
