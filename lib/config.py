""" arguments definition """

import argparse

from lib.utils import read_num_of_lines, get_max_len

def params_setup():
    """ arguments definition """

    parser = argparse.ArgumentParser()
    parser.add_argument('--nn', type=str, default='cnn', help='')
    parser.add_argument('--mode', type=str, default='train', help='')

    # parameters for multi-task seq2seq
    parser.add_argument('--attention_mode', type=str, default='luong', help='')
    parser.add_argument('--learning_rate', type=float, default=0.5, help='')
    parser.add_argument('--rl_learning_rate', type=float, default=0.0005, help='')
    parser.add_argument('--init_weight', type=float, default=0.1, help='')
    parser.add_argument('--max_gradient_norm', type=float, default=5.0, help='')
    parser.add_argument('--num_units', type=int, default=128, help='')
    parser.add_argument('--num_layers', type=int, default=2, help='')
    parser.add_argument('--batch_size', type=int, default=32, help='')
    parser.add_argument('--encoder_vocab_size', type=int, default=-1, help='')
    parser.add_argument('--decoder_vocab_size', type=int, default=-1, help='')
    parser.add_argument('--artist_size', type=int, default=-1, help='')
    parser.add_argument('--genre_size', type=int, default=-1, help='')
    parser.add_argument('--embedding_size', type=int, default=128, help='')
    parser.add_argument('--max_len', type=int, default=210, help='')
    parser.add_argument('--debug', type=int, default=0, help='')
    parser.add_argument('--beam_search', type=int, default=1, help='')
    parser.add_argument('--beam_width', type=int, default=1, help='')
    parser.add_argument('--num_samples', type=int, default=0, help='')
    parser.add_argument('--dropout', type=float, default=0.2, help='')
    parser.add_argument("--start_decay_step", type=int, default=20000, help='')
    parser.add_argument('--decay_steps', type=int, default=10000, help='')
    parser.add_argument('--decay_factor', type=float, default=0.98, help='')
    parser.add_argument('--steps_per_stats', type=int, default=10, help='')
    parser.add_argument('--scheduled_sampling', type=int, default=1, help='')
    parser.add_argument('--model_dir', type=str, default='models', help='')
    parser.add_argument('--rl', type=int, default=0, help='')

    # parameters for cnn
    parser.add_argument('--batch_norm', type=int, default=1, help='')

    para = parser.parse_args()

    para.encoder_vocab_size = read_num_of_lines('data/vocab_default.txt')
    para.decoder_vocab_size = read_num_of_lines('data/vocab_default.txt')
    para.artist_size = read_num_of_lines('data/artist.txt')
    para.genre_size = read_num_of_lines('data/genre.txt')

    if para.nn == 'rnn':
        para.max_len -= 1
    if para.nn == 'cnn':
        para.start_decay_step = 5000
        para.decay_steps = 5000

    if para.debug == 1:
        para.num_units = 14
        para.num_layers = 2
        para.batch_size = 2
        para.embedding_size = 14 # let cnn have a valid debug mode
    if para.mode == 'rl' or para.mode == 'test' or para.mode == 'valid':
        para.dropout = 0.0

    if para.model_dir == 'models':
        para.model_dir = './' + para.nn + '_' + para.model_dir

    rl_mode = para.model_dir[len(para.model_dir) - 2:]
    if para.mode == 'rl' and rl_mode != 'rl':
        para.model_dir += '_rl'

    if para.mode == 'test':
        para.batch_size = read_num_of_lines('results/in.txt')

    return para
