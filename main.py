""" main function """

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import time

import tensorflow as tf
import numpy as np

from lib.config import params_setup
from lib.utils import read_testing_sequences, word_id_to_song_id
from lib.utils import reward_functions
from lib.multi_task_seq2seq_model import Multi_Task_Seq2Seq
from lib.srcnn_model import SRCNN

def config_setup():
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True
    config.allow_soft_placement = True
    return config

def load_pretrain(sess):
    # only when these is no model under model_dir, this funciont will be called
    pre_train_dir = para.model_dir[:len(para.model_dir) - 3]
    print('Loading model from %s' % pre_train_dir)
    ckpt = tf.train.get_checkpoint_state(pre_train_dir)
    pre_train_saver.restore(sess, ckpt.model_checkpoint_path)

if __name__ == "__main__":
    para = params_setup()

    if para.nn == 'rnn' and para.mode == 'rl':
        raise NameError('there is no support of RL on rnn')

    with tf.Graph().as_default():
        initializer = tf.random_uniform_initializer(
            -para.init_weight, para.init_weight
        )
        if para.nn == 'rnn':
            with tf.variable_scope('model', reuse=None, initializer=initializer):
                model = Multi_Task_Seq2Seq(para)
                pretrained_variables = tf.get_collection(
                    tf.GraphKeys.TRAINABLE_VARIABLES,
                    scope='model'
                )
        elif para.nn == 'cnn':
            with tf.variable_scope('model', reuse=None, initializer=initializer):
                model = SRCNN(para)
                pretrained_variables = tf.get_collection(
                    tf.GraphKeys.TRAINABLE_VARIABLES,
                    scope='model'
                )
        if para.nn == 'cnn':
            for var in pretrained_variables:
                print("\t{}\t{}".format(var.name, var.get_shape()))
            pre_train_saver = tf.train.Saver(pretrained_variables)

        try:
            os.makedirs(para.model_dir)
        except os.error:
            pass

        print(para)

        if para.nn == 'rnn':
            sv = tf.train.Supervisor(logdir=para.model_dir)
        elif para.nn == 'cnn':
            if para.mode == 'valid' or para.mode == 'test':
                sv = tf.train.Supervisor(logdir=para.model_dir, save_model_secs=0)
            elif para.mode == 'train':
                sv = tf.train.Supervisor(logdir=para.model_dir)
            else:
                sv = tf.train.Supervisor(logdir=para.model_dir, init_fn=load_pretrain)
        with sv.managed_session(config=config_setup()) as sess:
            para_file = open('%s/para.txt' % (para.model_dir), 'w')
            para_file.write(str(para))
            para_file.close()

            if para.mode == 'train':
                step_time = 0.0
                for step in range(20000):
                    if sv.should_stop():
                        break
                    start_time = time.time()

                    [loss, predict_count, _] = sess.run(
                        fetches=[
                            model.loss,
                            model.predict_count,
                            model.update,
                        ],
                    )

                    loss = loss * para.batch_size
                    perplexity = np.exp(loss / predict_count)

                    step_time += (time.time() - start_time)
                    if step % para.steps_per_stats == 0:
                        print('step: %d, perplexity: %.2f step_time: %.2f' %
                            (step, perplexity, step_time / para.steps_per_stats))
                        step_time = 0
                    break

            elif para.mode == 'rl':
                step_time = 0.0
                for step in range(20000):
                    if sv.should_stop():
                        break
                    start_time = time.time()

                    # get input data
                    data = sess.run([
                        model.raw_encoder_inputs,
                        model.raw_encoder_inputs_len,
                        model.raw_seed_song_inputs,
                    ])
                    data = [e.astype(np.int32) for e in data]

                    # get sampled ids
                    [sampled_ids] = sess.run(
                        fetches=[
                            model.sampled_ids,
                        ],
                        feed_dict={
                            model.encoder_inputs: data[0],
                            model.encoder_inputs_len: data[1],
                            model.seed_song_inputs: data[2],
                        }
                    )

                    # get reward
                    rewards = reward_functions(para, sampled_ids)

                    # feed rewards and update the model
                    _ = sess.run(
                        fetches=[
                            model.rl_update,
                        ],
                        feed_dict={
                            model.encoder_inputs: data[0],
                            model.encoder_inputs_len: data[1],
                            model.seed_song_inputs: data[2],
                            model.sampled_ids_inputs: sampled_ids,
                            model.rewards: rewards
                        }
                    )

                    step_time += (time.time() - start_time)
                    if step % para.steps_per_stats == 0:
                        print('step: %d, reward: %.2f step_time: %.2f' %
                            (step, np.mean(rewards), step_time / para.steps_per_stats))
                        step_time = 0
                    break

            elif para.mode =='valid':
                for i in range(10):
                    [loss, predict_count] = sess.run([
                        model.loss,
                        model.predict_count,
                    ])
                    loss = loss * para.batch_size
                    perplexity = np.exp(loss / predict_count)
                    print('perplexity: %.2f' % perplexity)

            elif para.mode == 'test':
                encoder_inputs, encoder_inputs_len, seed_song_inputs = \
                    read_testing_sequences(para)

                [predicted_ids, decoder_outputs] = sess.run(
                    fetches=[
                        model.decoder_predicted_ids,
                        model.decoder_outputs,
                    ],
                    feed_dict={
                        model.encoder_inputs: encoder_inputs,
                        model.encoder_inputs_len: encoder_inputs_len,
                        model.seed_song_inputs: seed_song_inputs,
                    }
                )
                print(predicted_ids.shape)

                output_file = open('results/{}_out.txt'.format(para.nn), 'w')
                output_file.write(word_id_to_song_id(para, predicted_ids))
                output_file.close()
