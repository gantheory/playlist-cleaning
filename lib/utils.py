""" data processing functions """
import numpy as np
from copy import deepcopy
from collections import defaultdict

__all__ = ['word_id_to_song_id', 'read_testing_sequences', 'read_num_of_lines']

dictionary_path = 'data/vocab_default.txt'

def read_dictionary():
    dict_file = open(dictionary_path, 'r').read().splitlines()
    dict_file = [(word, i) for i, word in enumerate(dict_file)]
    dic = defaultdict(lambda: 3)
    for word, idx in dict_file:
        dic[word] = idx
    return dic

def numpy_array_to_list(array):
    if isinstance(array, np.ndarray):
        return numpy_array_to_list(array.tolist())
    elif isinstance(array, list):
        return [numpy_array_to_list(element) for element in array]
    else:
        return array

def read_num_of_lines(file_name):
    seqs = open(file_name, 'r').read().splitlines()
    return len(seqs)

def read_testing_sequences(para):
    # filter for smybol that utf8 cannot decode
    input_file = open('results/in.txt', 'r')
    output_file = open('results/in_filtered.txt', 'w')
    for line in input_file:
        output_file.write(bytes(line, 'utf-8').decode('utf-8', 'ignore'))
    input_file.close()
    output_file.close()
    seqs = open('results/in_filtered.txt', 'r').read().splitlines()
    seqs = [seq.split(' ') for seq in seqs]

    dic = read_dictionary()
    # input of seed ids
    seed_ids = open('results/seed.txt', 'r').read().splitlines()
    seed_ids = [dic[ID] for ID in seed_ids]

    seqs = [[dic[word] for word in seq] for seq in seqs]
    seqs = [seq + [2] for seq in seqs]
    if para.debug == 1:
        debug_dic = read_dictionary()
        for seq in seqs:
            seq = [debug_dic[word] for word in seq]
            print(seq)

    seqs_len = [len(seq) for seq in seqs]
    seqs = [np.array(seq + [0] * (para.max_len - len(seq))) for seq in seqs]
    para.batch_size = len(seqs)
    print('total num of sequences: %d' % len(seqs))

    return np.asarray(seqs), np.asarray(seqs_len), np.asarray(seed_ids)

def check_valid_song_id(song_id):
    return True
    filter_list = [ 0, 1, 2, 3, -1]
    return not song_id in filter_list

def word_id_to_song_id(para, predicted_ids):
    dic = open(dictionary_path, 'r').read().splitlines()
    # predicted_ids: [batch_size, <= max_len, beam_width]
    predicted_ids = numpy_array_to_list(predicted_ids)

    # song_id_seqs: [num_of_data * beam_width, <= max_len]
    song_id_seqs = []
    for seq in predicted_ids:
        for i in range(para.beam_width):
            song_id_seqs.append([seq[j][i] for j in range(len(seq))])
    song_id_seqs = [
        [dic[song_id] for song_id in seq if check_valid_song_id(song_id)]
        for seq in song_id_seqs
    ]
    # song_id_seqs = [list(set(seq)) for seq in song_id_seqs]

    return '\n'.join([' '.join(seq) for seq in song_id_seqs])
