import json
import os
import mido

from math import isclose
from tqdm import tqdm


def extract_one(deemo: dict) -> list:
    """
    Converts a Deemo song dict to a list of notes.
    The Deemo song dict is obtained directly from reading the Deemo song json file.
    Each note in the list is in the form of [on_time, off_time, pitch, velocity].
    Time is absolute time in seconds.

    :param deemo: Deemo song dict
    :return: list of notes
    """
    converted_notes = []
    deemo_notes = deemo['notes']
    for deemo_note in deemo_notes:
        # Skip if there is no sounds
        if 'sounds' not in deemo_note.keys():
            continue
        # Handle missing _time at the start of the song
        time = 0
        if '_time' in deemo_note.keys():
            time = deemo_note['_time']
        for sound in deemo_note['sounds']:
            # w is a relative delay of onset on top of _time
            if 'w' in sound.keys():
                on_time = time + sound['w']
            else:
                on_time = time
            # Handle missing d
            if 'd' not in sound.keys():
                # This is based on the assumption that there exists a previous note
                # and the duration of the previous note is the same as the current note.
                # Otherwise, it makes little sense to have a note without a duration.
                # However, if this assumption is wrong, then we may run into an exception.
                previous_note = converted_notes[-1]
                duration = previous_note[1] - previous_note[0]
            else:
                duration = sound['d']
            off_time = on_time + duration
            pitch = sound['p']
            velocity = sound['v']
            converted_notes.append([on_time, off_time, pitch, velocity])
    # Sort the notes by on_time, then by ascending pitch
    converted_notes.sort(key=lambda x: (x[0], x[2]))

    return converted_notes


def load_json(filename):
    """
    Loads a json file.

    :param filename: The path to the json file.
    :return: The loaded json file.
    """
    with open(filename, 'r') as f:
        return json.load(f)


def save_json(converted_notes, filename):
    """
    Saves a list of notes to a json file.

    :param converted_notes: A list of notes, where each note is a list of [start_time, end_time, pitch, velocity].
    :param filename: The path to the json file.
    """
    with open(filename, 'w') as f:
        json.dump(converted_notes, f, indent=2)


def is_equal(notes_a, notes_b):
    """
    Compares two lists of notes and returns True if they are equal, False otherwise.

    :param notes_a: list of notes
    :param notes_b: list of notes
    :return: True if notes_a == notes_b, False otherwise
    """
    if len(notes_a) != len(notes_b):
        print(f'Length mismatch: {len(notes_a)} != {len(notes_b)}')
        return False
    num_unmatch = 0
    for i in range(len(notes_a)):
        if not isclose(notes_a[i][0], notes_b[i][0], rel_tol=1e-5) or \
                not isclose(notes_a[i][1], notes_b[i][1], rel_tol=1e-5) or \
                notes_a[i][2] != notes_b[i][2] or \
                notes_a[i][3] != notes_b[i][3]:
            num_unmatch += 1
            # print(f'Mismatch at index {i}:\n{notes_a[i]}\n{notes_b[i]}')

    if num_unmatch > 0:
        # print(f'{num_unmatch}/{len(notes_a)} ({num_unmatch / len(notes_a) * 100:.2f}%) notes do not match.')
        return False
    return True


def list_to_midi(notes) -> mido.MidiFile:
    """
    Converts a list of notes to a midi file.

    :param notes: A list of notes, where each note is a list of [start_time, end_time, pitch, velocity].
    :return: A mido.MidiFile object.
    """
    ticks_per_beat = 480  # default to 480
    tempo = mido.bpm2tempo(120.0)  # default to 120 bpm

    mid = mido.MidiFile()
    mid.ticks_per_beat = ticks_per_beat
    track = mido.MidiTrack()
    mid.tracks.append(track)

    track.append(mido.MetaMessage('set_tempo', tempo=tempo))
    track.append(mido.Message('program_change', program=0, time=0))

    # Split notes into on and off messages, and convert all seconds to ticks
    note_events = []  # [ticks, pitch, velocity, ticks], where note_events[0] to be converted to delta_ticks
    for note in notes:
        start_time, end_time, pitch, velocity = note
        start_ticks = round(mido.second2tick(start_time, ticks_per_beat, tempo))
        end_ticks = round(mido.second2tick(end_time, ticks_per_beat, tempo))
        note_events.append([start_ticks, pitch, velocity, start_ticks])
        note_events.append([end_ticks, pitch, 0, end_ticks])

    # Sort note events by ascending order of ticks, then by ascending order of pitch,
    # then by ascending order of velocity
    note_events.sort(key=lambda x: (x[0], x[1], x[2]))

    # Absolute ticks to relative ticks
    for i in range(1, len(note_events)):
        note_events[i][0] = note_events[i][-1] - note_events[i - 1][-1]  # [delta_ticks, pitch, velocity, ticks]

    # Add notes
    for note_event in note_events:
        delta_ticks, pitch, velocity, _ = note_event
        track.append(mido.Message('note_on', note=pitch, velocity=velocity, time=delta_ticks))

    # Add end of track
    track.append(mido.MetaMessage('end_of_track', time=1))

    return mid


def compare_difficulty_old(songs_dir):
    """
    Iterates through all the songs in the directory and compares the notes of different difficulties
    to see if they are the same.

    :param songs_dir: The directory containing the Deemo songs.
    :return: None
    """
    songs = os.listdir(songs_dir)
    mismatched_songs = []
    for song in tqdm(songs):
        files = os.listdir(os.path.join(songs_dir, song))
        # Only keep the json files
        files = [f for f in files if os.path.splitext(f)[1] == '.json' or os.path.splitext(f)[1] == '.txt']
        try:
            notes_list = [extract_one(load_json(os.path.join(songs_dir, song, f))) for f in files]
            assert len(notes_list) > 1, f'{song} has less than 2 difficulties.'
        except Exception as e:
            print(f'Error reading {song}: {e}')
            continue
        # Compare the i-th difficulty with the (i+1)-th difficulty
        for i in range(len(notes_list) - 1):
            if not is_equal(notes_list[i], notes_list[i + 1]):
                mismatched_songs.append(song)
                # print(f'{song} has different notes between {files[i]} and {files[i + 1]}')
    # Deduplicate the mismatched songs
    mismatched_songs = list(set(mismatched_songs))
    print('Comparison done.')
    print(f'{len(mismatched_songs)} songs have different notes between difficulties.')


def compare_difficulty(song_paths, verbose=False) -> bool:
    """
    Checks whether the notes of different difficulties of a single song are the same.

    :param song_paths: A list of paths to the json files of the different difficulties of a single song.
    :param verbose: Whether to print the mismatched notes.
    :return: True if the notes are the same, False otherwise.
    """
    notes_list = [extract_one(load_json(song_path)) for song_path in song_paths]
    # Compare the i-th difficulty with the (i+1)-th difficulty
    for i in range(len(notes_list) - 1):
        if not is_equal(notes_list[i], notes_list[i + 1]):
            if verbose:
                print(f'{song_paths[i]} and {song_paths[i + 1]} have different notes.')
            return False
    return True


def extract_songs(songs_dir, output_dir, one_only=False):
    """
    Converts all the Deemo songs in the directory to midi files.

    :param songs_dir: The directory containing the Deemo songs.
    :param output_dir: The directory to save the midi files.
    :param one_only: Whether to randomly convert only one difficulty to midi even if the notes are not the same.
    :return: None
    """
    songs = os.listdir(songs_dir)
    for song in tqdm(songs):
        files = os.listdir(os.path.join(songs_dir, song))
        # Only keep the json files
        files = [f for f in files if os.path.splitext(f)[1] == '.json' or os.path.splitext(f)[1] == '.txt']
        if len(files) < 2:
            print(f'Skipping {song} because it has less than 2 difficulties.')
            continue
        file_paths = [os.path.join(songs_dir, song, f) for f in files]
        try:
            if one_only or compare_difficulty(file_paths):
                # If the notes are the same, we only need to convert one of the difficulties
                notes = extract_one(load_json(file_paths[0]))
                midi = list_to_midi(notes)
                midi.save(os.path.join(output_dir, f'{song}.mid'))
            else:
                # If the notes are different, we need to convert all the difficulties
                for f in files:
                    notes = extract_one(load_json(os.path.join(songs_dir, song, f)))
                    midi = list_to_midi(notes)
                    midi.save(os.path.join(output_dir, f'{os.path.splitext(f)[0]}.mid'))
        except Exception as e:
            print(f'Error converting {song}: {e}')


def test():
    # with open('../songs/hard.json.json', 'r') as f:
    #     hard = json.load(f)

    # with open('../songs/easy.json.json', 'r') as f:
    #     easy = json.load(f)

    # hard_notes = deemo_to_list(hard)
    # midi = list_to_midi(hard_notes)
    # midi.save('test.mid')
    # easy_notes = deemo_to_list(easy)
    # print(is_equal(hard_notes, easy_notes))

    compare_difficulty_old('../songs')

    # extract_songs('../songs', './converted/one_only', one_only=True)

    with open('../songs5/easy.json.txt', 'r') as f:
        easy = json.load(f)

    notes = extract_one(easy)
    midi = list_to_midi(notes)
    midi.save('test.mid')


def main():
    test()


if __name__ == '__main__':
    main()
