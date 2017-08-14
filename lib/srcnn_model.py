""" srcnn model """

from copy import deepcopy

import tensorflow as tf
import tensorflow.contrib.seq2seq as seq2seq
from tensorflow.python.layers.core import dense

from lib.utils import read_num_of_lines

class SRCNN():
    def __init__(self, para):
        self.para = para
        self.dtype = tf.float32
        self.global_step = tf.Variable(0, trainable=False, name='global_step')

        self.build_weights()
        if self.para.mode == 'train':
            print('build training graph')
            with tf.name_scope('train'):
                self.set_input()
                self.build_graph()
                self.build_optimizer()

                tf.get_variable_scope().reuse_variables()
                self.build_valid_graph()

        elif self.para.mode == 'rl':
            print('build reinforcement learning graph')
            with tf.name_scope('rl'):
                self.set_input()
                self.build_graph()
                self.build_rl_optimizer()

        elif self.para.mode == 'valid':
            print('build validation graph')
            with tf.name_scope('valid'):
                self.set_input()
                self.build_graph()

        elif self.para.mode == 'test':
            print('build testing graph')
            with tf.name_scope(''):
                self.set_input()
                self.build_graph()

        # saver must be called after all definition of variables
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
            sampled_ids_inputs:[batch_size, max_len]
            rewards: [batch_size]
        """

        print('set input nodes...')
        if self.para.mode == 'train' or self.para.mode == 'valid':
            self.raw_encoder_inputs, self.raw_encoder_inputs_len, \
            self.raw_decoder_inputs, self.raw_decoder_inputs_len, \
            self.raw_seed_song_inputs = self.read_batch_sequences(self.para.mode)

            self.encoder_inputs = self.raw_encoder_inputs
            self.encoder_inputs_len = self.raw_encoder_inputs_len
            self.seed_song_inputs = self.raw_seed_song_inputs
            self.decoder_inputs = self.raw_decoder_inputs
            self.decoder_inputs_len = self.raw_decoder_inputs_len
            self.decoder_targets = self.raw_decoder_inputs

            self.predict_count = tf.reduce_sum(self.decoder_inputs_len)

            if self.para.mode == 'train':
                self.valid_encoder_inputs = tf.placeholder(
                    dtype=tf.int32, shape=(None, self.para.max_len),
                    name='valid_encoder_inputs'
                )
                self.valid_seed_song_inputs = tf.placeholder(
                    dtype=tf.int32, shape=(None,),
                    name='valid_seed_song_inputs'
                )
                self.valid_decoder_targets = tf.placeholder(
                    dtype=tf.int32, shape=(None, self.para.max_len),
                    name='valid_decoder_targets'
                )

        elif self.para.mode == 'rl':
            self.raw_encoder_inputs, self.raw_encoder_inputs_len, _, _, \
            self.raw_seed_song_inputs = self.read_batch_sequences('train')

            self.encoder_inputs = tf.placeholder(
                dtype=tf.int32, shape=(None, self.para.max_len),
                name='encoder_inputs'
            )
            self.encoder_inputs_len = tf.placeholder(
                dtype=tf.int32, shape=(None,),
                name='encoder_inputs_len'
            )
            self.seed_song_inputs = tf.placeholder(
                dtype=tf.int32, shape=(None,),
                name='seed_song_inputs'
            )
            self.sampled_ids_inputs = tf.placeholder(
                dtype=tf.int32, shape=(None, self.para.max_len),
                name='sampled_ids_inputs'
            )
            self.rewards = tf.placeholder(
                dtype=self.dtype, shape=(None,),
                name='rewards'
            )

        elif self.para.mode == 'test':
            self.encoder_inputs = tf.placeholder(
                dtype=tf.int32, shape=(None, self.para.max_len),
                name='encoder_inputs'
            )
            self.encoder_inputs_len = tf.placeholder(
                dtype=tf.int32, shape=(None,),
                name='encoder_inputs_len'
            )
            self.seed_song_inputs = tf.placeholder(
                dtype=tf.int32, shape=(None,),
                name='seed_song_inputs'
            )

    def build_graph(self):
        self.encoder_embedding = tf.get_variable(
            name='encoder_embedding',
            shape=[self.para.encoder_vocab_size, self.para.embedding_size],
            dtype=self.dtype
        )
        # self.seed_song_embedded: [batch_size, embedding_size]
        self.seed_song_embedded = tf.nn.embedding_lookup(
            params=self.encoder_embedding,
            ids=self.seed_song_inputs
        )
        self.seed_song_embedded = tf.reshape(
            self.seed_song_embedded,
            [self.para.batch_size, 1, self.para.embedding_size, 1]
        )
        self.encoder_inputs_embedded = tf.nn.embedding_lookup(
            params=self.encoder_embedding,
            ids=self.encoder_inputs
        )
        # self.encoder_inputs_embedded: [batch_size, max_len, embedding_size, 1]
        self.encoder_inputs_embedded = tf.reshape(
            self.encoder_inputs_embedded,
            [self.para.batch_size, self.para.max_len, self.para.embedding_size, 1]
        )
        inputs_shape = tf.shape(self.encoder_inputs_embedded)

        print('SRCNN\'s input: ' , end='')
        print(self.encoder_inputs_embedded.get_shape())
        conv1 = tf.nn.conv2d(
            input=self.encoder_inputs_embedded,
            filter=self.weights['w1'],
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        print('After 1st convolution: ', end='')
        print(conv1.get_shape())
        if self.para.batch_norm == 1:
            conv1_bn = self.batch_normalization(
                conv1,
                self.offsets['o1'],
                self.scales['s1'],
                'conv1'
            )
        conv1_relu = tf.nn.relu(conv1_bn + self.biases['b1'])
        conv1_relu = tf.nn.dropout(
            conv1_relu,
            keep_prob=(1.0 - self.para.dropout)
        )
        conv2 = tf.nn.conv2d(
            input=conv1_relu,
            filter=self.weights['w2'],
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        print('After 2nd convolution: ', end='')
        print(conv2.get_shape())
        if self.para.batch_norm == 1:
            conv2_bn = self.batch_normalization(
                conv2,
                self.offsets['o2'],
                self.scales['s2'],
                'conv2'
            )
        conv2_relu = tf.nn.relu(conv2_bn + self.biases['b2'])
        conv2_relu = tf.nn.dropout(
            conv2_relu,
            keep_prob=(1.0 - self.para.dropout)
        )
        conv3 = tf.nn.conv2d(
            input=conv2_relu,
            filter=self.weights['w3'],
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        print('After 3rd convolution: ', end='')
        print(conv3.get_shape())
        if self.para.batch_norm == 1:
            conv3_bn = self.batch_normalization(
                conv3,
                self.offsets['o3'],
                self.scales['s3'],
                'conv3'
            )
        conv3_relu = tf.nn.relu(conv3_bn + self.biases['b3'])
        conv3_relu = tf.nn.dropout(
            conv3_relu,
            keep_prob=(1.0 - self.para.dropout)
        )
        inv_conv3 = tf.nn.conv2d_transpose(
            conv3_relu,
            self.weights['inv_w3'],
            tf.shape(conv2_relu),
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        inv_conv3 = self.residual(inv_conv3, conv2)
        print('After 1st deconvolution: ', end='')
        print(inv_conv3.get_shape())
        if self.para.batch_norm == 1:
            inv_conv3_bn = self.batch_normalization(
                inv_conv3,
                self.offsets['inv_o3'],
                self.scales['inv_s3'],
                'inv_conv3'
            )
        inv_conv3_relu = tf.nn.relu(inv_conv3_bn + self.biases['inv_b3'])
        inv_conv3_relu = tf.nn.dropout(
            inv_conv3_relu,
            keep_prob=(1.0 - self.para.dropout)
        )
        inv_conv2 = tf.nn.conv2d_transpose(
            inv_conv3_relu,
            self.weights['inv_w2'],
            tf.shape(conv1_relu),
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        inv_conv2 = self.residual(inv_conv2, conv1)
        print('After 2nd deconvolution: ', end='')
        print(inv_conv2.get_shape())
        if self.para.batch_norm == 1:
            inv_conv2_bn = self.batch_normalization(
                inv_conv2,
                self.offsets['inv_o2'],
                self.scales['inv_s2'],
                'inv_conv2'
            )
        inv_conv2_relu = tf.nn.relu(inv_conv2_bn + self.biases['inv_b2'])
        inv_conv2_relu = tf.nn.dropout(
            inv_conv2_relu,
            keep_prob=(1.0 - self.para.dropout)
        )
        inv_conv1 = tf.nn.conv2d_transpose(
            inv_conv2_relu,
            self.weights['inv_w1'],
            inputs_shape,
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        self.residual_outputs = self.residual(
            inv_conv1, self.encoder_inputs_embedded
        )
        self.residual_outputs = self.residual(
            self.residual_outputs, self.seed_song_embedded
        )
        print('After 3rd deconvolution: ', end='')
        print(inv_conv1.get_shape())
        if self.para.batch_norm == 1:
            inv_conv1_bn = self.batch_normalization(
                inv_conv1,
                self.offsets['inv_o1'],
                self.scales['inv_s1'],
                'inv_conv1'
            )
        inv_conv1_relu = tf.nn.relu(inv_conv1_bn + self.biases['inv_b1'])
        inv_conv1_relu = tf.nn.dropout(
            inv_conv1_relu,
            keep_prob=(1.0 - self.para.dropout)
        )
        self.embedding_outputs = tf.reshape(
            self.residual_outputs,
            [self.para.batch_size, self.para.max_len, self.para.embedding_size]
        )
        self.outputs = dense(
            inputs=self.embedding_outputs,
            units=self.para.decoder_vocab_size,
            name='output_projection'
        )

        if self.para.mode == 'train' or self.para.mode == 'valid':
            self.loss = self.compute_loss(
                logits=self.outputs,
                labels=self.decoder_targets
            )
        elif self.para.mode == 'rl':
            self.sampled_ids = self.get_sampled_ids(self.outputs)

            self.loss = self.compute_rl_loss(
               logits=self.outputs,
               labels=self.sampled_ids_inputs
            )
        elif self.para.mode == 'test':
            # compatible with the rnn model
            self.decoder_outputs = self.outputs
            self.decoder_predicted_ids = self.get_predicted_ids(self.outputs)

    def build_valid_graph(self):
        self.encoder_embedding = tf.get_variable(
            name='encoder_embedding',
            shape=[self.para.encoder_vocab_size, self.para.embedding_size],
            dtype=self.dtype
        )
        # self.seed_song_embedded: [batch_size, embedding_size]
        seed_song_embedded = tf.nn.embedding_lookup(
            params=self.encoder_embedding,
            ids=self.valid_seed_song_inputs
        )
        seed_song_embedded = tf.reshape(
            seed_song_embedded,
            [self.para.batch_size, 1, self.para.embedding_size, 1]
        )
        encoder_inputs_embedded = tf.nn.embedding_lookup(
            params=self.encoder_embedding,
            ids=self.valid_encoder_inputs
        )
        # self.encoder_inputs_embedded: [batch_size, max_len, embedding_size, 1]
        encoder_inputs_embedded = tf.reshape(
            encoder_inputs_embedded,
            [self.para.batch_size, self.para.max_len, self.para.embedding_size, 1]
        )
        inputs_shape = tf.shape(encoder_inputs_embedded)

        valid_conv1 = tf.nn.conv2d(
            input=encoder_inputs_embedded,
            filter=self.weights['w1'],
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        if self.para.batch_norm == 1:
            valid_conv1_bn = self.batch_normalization(
                valid_conv1,
                self.offsets['o1'],
                self.scales['s1'],
                'conv1'
            )
        valid_conv1_relu = tf.nn.relu(valid_conv1_bn + self.biases['b1'])
        valid_conv2 = tf.nn.conv2d(
            input=valid_conv1_relu,
            filter=self.weights['w2'],
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        if self.para.batch_norm == 1:
            valid_conv2_bn = self.batch_normalization(
                valid_conv2,
                self.offsets['o2'],
                self.scales['s2'],
                'conv2'
            )
        valid_conv2_relu = tf.nn.relu(valid_conv2_bn + self.biases['b2'])
        valid_conv3 = tf.nn.conv2d(
            input=valid_conv2_relu,
            filter=self.weights['w3'],
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        if self.para.batch_norm == 1:
            valid_conv3_bn = self.batch_normalization(
                valid_conv3,
                self.offsets['o3'],
                self.scales['s3'],
                'conv3'
            )
        valid_conv3_relu = tf.nn.relu(valid_conv3_bn + self.biases['b3'])
        valid_inv_conv3 = tf.nn.conv2d_transpose(
            valid_conv3_relu,
            self.weights['inv_w3'],
            tf.shape(valid_conv2_relu),
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        valid_inv_conv3 = self.residual(valid_inv_conv3, valid_conv2)
        if self.para.batch_norm == 1:
            valid_inv_conv3_bn = self.batch_normalization(
                valid_inv_conv3,
                self.offsets['inv_o3'],
                self.scales['inv_s3'],
                'inv_conv3'
            )
        valid_inv_conv3_relu = tf.nn.relu(valid_inv_conv3_bn + self.biases['inv_b3'])
        valid_inv_conv2 = tf.nn.conv2d_transpose(
            valid_inv_conv3_relu,
            self.weights['inv_w2'],
            tf.shape(valid_conv1_relu),
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        valid_inv_conv2 = self.residual(valid_inv_conv2, valid_conv1)
        if self.para.batch_norm == 1:
            valid_inv_conv2_bn = self.batch_normalization(
                valid_inv_conv2,
                self.offsets['inv_o2'],
                self.scales['inv_s2'],
                'inv_conv2'
            )
        valid_inv_conv2_relu = tf.nn.relu(valid_inv_conv2_bn + self.biases['inv_b2'])
        valid_inv_conv1 = tf.nn.conv2d_transpose(
            valid_inv_conv2_relu,
            self.weights['inv_w1'],
            inputs_shape,
            strides=[1, 1, 1, 1],
            padding='VALID'
        )
        residual_outputs = self.residual(
            valid_inv_conv1, encoder_inputs_embedded
        )
        residual_outputs = self.residual(
            residual_outputs, seed_song_embedded
        )
        if self.para.batch_norm == 1:
            valid_inv_conv1_bn = self.batch_normalization(
                valid_inv_conv1,
                self.offsets['inv_o1'],
                self.scales['inv_s1'],
                'inv_conv1'
            )
        valid_inv_conv1_relu = tf.nn.relu(valid_inv_conv1_bn + self.biases['inv_b1'])
        embedding_outputs = tf.reshape(
            residual_outputs,
            [self.para.batch_size, self.para.max_len, self.para.embedding_size]
        )
        outputs = dense(
            inputs=embedding_outputs,
            units=self.para.decoder_vocab_size,
            name='output_projection'
        )

        self.valid_loss = self.compute_loss(
            logits=outputs,
            labels=self.valid_decoder_targets
        )
        self.valid_loss /= self.para.max_len
        self.valid_predicted_ids = self.get_predicted_ids(outputs)

    def residual(self, x, y):
        return tf.add(x, y)

    def batch_normalization(self, input_tensor, offset, scale, name):
        """ global normalization """

        mean, variance = tf.nn.moments(input_tensor, [0, 1, 2])
        input_tensor_norm = tf.nn.batch_normalization(
            x=input_tensor,
            mean=mean,
            variance=variance,
            offset=offset,
            scale=scale,
            variance_epsilon=1e-8,
            name=name
        )
        return input_tensor_norm

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

    def compute_rl_loss(self, logits, labels):
        """
            logits: [batch_size, max_len, decoder_vocab_size]
            labels: [batch_size, max_len]
        """
        # log_p: [batch_size, max_len, decoder_vocab_size]
        log_p = -tf.log(
            tf.add(tf.nn.softmax(logits), tf.constant(1e-8, dtype=self.dtype))
        )
        # labels: [batch_size, max_len, decoder_vocab_size]
        labels = tf.one_hot(
            indices=labels,
            depth=self.para.decoder_vocab_size
        )
        # loss: [batch_size]
        loss = tf.reduce_sum(tf.multiply(log_p, labels), [1, 2])
        loss = tf.reduce_sum(tf.multiply(loss, self.rewards)) / \
               tf.to_float(self.para.batch_size)
        return loss

    def build_optimizer(self):
        self.optimizer = tf.train.AdamOptimizer()
        self.gradients = tf.gradients(self.loss, tf.trainable_variables())

        debug = tf.gradients(self.loss, tf.trainable_variables())
        self.debug = [i for i in debug if i != None]

        self.update = self.optimizer.apply_gradients(
            zip(self.gradients, tf.trainable_variables()),
            global_step=self.global_step
        )

    def build_rl_optimizer(self):
        self.rl_opt = tf.train.GradientDescentOptimizer(self.para.rl_learning_rate)
        self.gradients = tf.gradients(self.loss, tf.trainable_variables())

        # debug = tf.gradients(self.loss, tf.trainable_variables())
        # self.debug = []
        # for i in range(len(debug)):
        #     if debug[i] != None:
        #         self.debug.append((tf.trainable_variables(), debug[i]))

        self.rl_update = self.rl_opt.apply_gradients(
            zip(self.gradients, tf.trainable_variables()),
            global_step=self.global_step
        )

    def get_predicted_ids(self, outputs):
        ids = tf.argmax(outputs, axis=2)
        decoder_predicted_ids = tf.reshape(
            ids,
            [self.para.batch_size, self.para.max_len, 1]
        )
        return decoder_predicted_ids

    def get_sampled_ids(self, outputs):
        # outputs: [batch_size, max_len, decoder_vocab_size]
        outputs = tf.reshape(
            outputs,
            [self.para.batch_size * self.para.max_len, self.para.decoder_vocab_size]
        )
        ids = tf.multinomial(outputs, num_samples=1)
        sampled_ids = tf.reshape(ids, [self.para.batch_size, self.para.max_len])
        return sampled_ids

    def read_batch_sequences(self, mode):
        """ read a batch from .tfrecords """

        file_queue = tf.train.string_input_producer(
            ['./data/cnn_{}.tfrecords'.format(mode)]
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
        seed_ids = tf.reshape(seed_ids, [self.para.batch_size])

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

    def build_weights(self):
        self.weights = {
            'w1': tf.Variable(
                tf.random_normal([9, 9, 1, 64], stddev=1e-3),
                dtype=self.dtype,
                name='w1'
            ),
            'w2': tf.Variable(
                tf.random_normal([1, 1, 64, 32], stddev=1e-3),
                dtype=self.dtype,
                name='w1'
            ),
            'w3': tf.Variable(
                tf.random_normal([5, 5, 32, 1], stddev=1e-3),
                dtype=self.dtype,
                name='w1'
            ),
            'inv_w3': tf.Variable(
                tf.random_normal([5, 5, 32, 1], stddev=1e-3),
                dtype=self.dtype,
                name='inv_w3'
            ),
            'inv_w2': tf.Variable(
                tf.random_normal([1, 1, 64, 32], stddev=1e-3),
                dtype=self.dtype,
                name='inv_w2'
            ),
            'inv_w1': tf.Variable(
                tf.random_normal([9, 9, 1, 64], stddev=1e-3),
                dtype=self.dtype,
                name='inv_w1'
            ),
        }
        self.biases = {
            'b1': tf.Variable(
                tf.zeros([64]),
                dtype=self.dtype,
                name='b1'
            ),
            'b2': tf.Variable(
                tf.zeros([32]),
                dtype=self.dtype,
                name='b2'
            ),
            'b3': tf.Variable(
                tf.zeros([1]),
                dtype=self.dtype,
                name='b3'
            ),
            'inv_b3': tf.Variable(
                tf.zeros([32]),
                dtype=self.dtype,
                name='inv_b3'
            ),
            'inv_b2': tf.Variable(
                tf.zeros([64]),
                dtype=self.dtype,
                name='inv_b2'
            ),
            'inv_b1': tf.Variable(
                tf.zeros([1]),
                dtype=self.dtype,
                name='inv_b1'
            ),
        }
        self.offsets = {
            'o1': tf.get_variable(
                name='o1',
                shape=[64],
                dtype=self.dtype
            ),
            'o2': tf.get_variable(
                name='o2',
                shape=[32],
                dtype=self.dtype
            ),
            'o3': tf.get_variable(
                name='o3',
                shape=[1],
                dtype=self.dtype
            ),
            'inv_o3': tf.get_variable(
                name='inv_o3',
                shape=[32],
                dtype=self.dtype
            ),
            'inv_o2': tf.get_variable(
                name='inv_o2',
                shape=[64],
                dtype=self.dtype
            ),
            'inv_o1': tf.get_variable(
                name='inv_o1',
                shape=[1],
                dtype=self.dtype
            ),
        }
        self.scales = {
            's1': tf.get_variable(
                name='s1',
                shape=[64],
                dtype=self.dtype
            ),
            's2': tf.get_variable(
                name='s2',
                shape=[32],
                dtype=self.dtype
            ),
            's3': tf.get_variable(
                name='s3',
                shape=[1],
                dtype=self.dtype
            ),
            'inv_s3': tf.get_variable(
                name='inv_s3',
                shape=[32],
                dtype=self.dtype
            ),
            'inv_s2': tf.get_variable(
                name='inv_s2',
                shape=[64],
                dtype=self.dtype
            ),
            'inv_s1': tf.get_variable(
                name='inv_s1',
                shape=[1],
                dtype=self.dtype
            ),
        }
