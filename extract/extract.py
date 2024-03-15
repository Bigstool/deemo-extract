import json
import os
import argparse
import mido

from typing import Tuple, List
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
        # Skip if sounds is None
        if deemo_note['sounds'] is None:
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
            # Handle v lower than 0
            # For some reason, there are notes with velocity lower than 0.
            # It is assumed that they don't make any sound, so we set them to 0.
            # However, if this assumption is wrong, then the velocity of these notes would be wrong.
            velocity = sound['v'] if 0 <= sound['v'] <= 127 else 0
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


def is_equal(notes_a, notes_b) -> Tuple[bool, str]:
    """
    Compares two lists of notes and returns True if they are equal, False otherwise.

    :param notes_a: list of notes
    :param notes_b: list of notes
    :return: A tuple of (bool, str), where the first element is True if the notes are equal, False otherwise,
             and the second element is a message indicating the result of the comparison.
    """
    if len(notes_a) != len(notes_b):
        return False, f'Length mismatch: {len(notes_a)} != {len(notes_b)}'
    num_unmatch = 0
    for i in range(len(notes_a)):
        if not isclose(notes_a[i][0], notes_b[i][0], rel_tol=1e-5) or \
                not isclose(notes_a[i][1], notes_b[i][1], rel_tol=1e-5) or \
                notes_a[i][2] != notes_b[i][2] or \
                notes_a[i][3] != notes_b[i][3]:
            num_unmatch += 1
            # print(f'Mismatch at index {i}:\n{notes_a[i]}\n{notes_b[i]}')

    if num_unmatch > 0:
        return False, f'Notes mismatch: {num_unmatch}/{len(notes_a)} ({num_unmatch / len(notes_a) * 100:.2f}%) notes.'
    return True, 'Notes are equal.'


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


def filter_files(files: List[str]) -> List[str]:
    """
    Filters the files to only keep the song json files.

    :param files: A list of file names.
    :return: A list of file names that are json files.
    """
    allowed_extensions = ['.json', '.txt']
    return [f for f in files if os.path.splitext(f)[1] in allowed_extensions]


def compare_difficulty(song_paths) -> Tuple[bool, str, List[List[list]]]:
    """
    Checks whether the notes of different difficulties of a single song are the same.

    :param song_paths: A list of paths to the json files of the different difficulties of a single song.
    :return: A tuple of (bool, str, List[List[list]]), where the first element is True if the notes are equal,
             False otherwise, the second element is a message indicating the result of the comparison,
             and the third element is a list of the extracted notes of the different difficulties.
    """
    notes_list = [extract_one(load_json(song_path)) for song_path in song_paths]
    # Compare the i-th difficulty with the (i+1)-th difficulty
    for i in range(len(notes_list) - 1):
        equal, message = is_equal(notes_list[i], notes_list[i + 1])
        if not equal:
            return False, message, notes_list
    return True, 'Notes are equal.', notes_list


def check_songs(songs_dir, suppress_length, suppress_notes) -> Tuple[List[str], List[str]]:
    """
    Iterates through all the songs in the directory and compares the notes of different difficulties
    to see if they are the same.

    :param songs_dir: The directory containing the Deemo songs.
    :param suppress_length: Whether to suppress the length mismatch messages.
    :param suppress_notes: Whether to suppress the notes mismatch messages.
    :return: A tuple of (List[str], List[str]), where the first element is a list of songs that have difficulties
             with different lengths, and the second element is a list of songs that have difficulties with different
             notes.
    """
    songs = os.listdir(songs_dir)
    length_mismatch_songs = []
    notes_mismatch_songs = []
    messages = []
    for song in tqdm(songs):
        files = os.listdir(os.path.join(songs_dir, song))
        # Only keep the json files
        files = filter_files(files)
        # Check the number of difficulties
        if len(files) < 2:
            messages.append(f'{song} has less than 2 difficulties.')
            continue
        # Attempt to extract the notes from the json files and compare them
        try:
            same, message, notes_list = compare_difficulty([os.path.join(songs_dir, song, f) for f in files])
        except Exception as e:
            messages.append(f'{song} Read error: {e}')
            continue
        if message.startswith('Length mismatch'):
            if not suppress_length:
                messages.append(f'{song} {message}')
            length_mismatch_songs.append(song)
        if message.startswith('Notes mismatch'):
            if not suppress_notes:
                messages.append(f'{song} {message}')
            notes_mismatch_songs.append(song)
        # Attempt to convert the notes to midi
        try:
            for notes in notes_list:
                _ = list_to_midi(notes)
        except Exception as e:
            messages.append(f'{song} Conversion error: {e}')
            continue
    # Print the messages
    for message in messages:
        print(message)
    # Deduplicate the mismatched songs
    length_mismatch_songs = list(set(length_mismatch_songs))
    notes_mismatch_songs = list(set(notes_mismatch_songs))
    print('Comparison done.')
    print(f'{len(length_mismatch_songs)}/{len(songs)} ({len(length_mismatch_songs) / len(songs) * 100:.2f}%) songs '
          f'have difficulties with different lengths.')
    print(f'{len(notes_mismatch_songs)}/{len(songs)} ({len(notes_mismatch_songs) / len(songs) * 100:.2f}%) songs '
          f'have difficulties with different notes.')
    return length_mismatch_songs, notes_mismatch_songs


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
        files = filter_files(files)
        if len(files) < 2:
            print(f'Skipping {song} because it has less than 2 difficulties.')
            continue
        try:
            same, _, notes_list = compare_difficulty([os.path.join(songs_dir, song, f) for f in files])
            if one_only or same:
                # If the notes are the same, we save the one with the most number of notes
                max_notes = max(notes_list, key=len)
                midi = list_to_midi(max_notes)
                midi.save(os.path.join(output_dir, f'{song}.mid'))
            else:
                # If the notes are different, we need to convert all the difficulties
                for i, notes in enumerate(notes_list):
                    midi = list_to_midi(notes)
                    midi.save(os.path.join(output_dir, f'{os.path.splitext(files[i])[0]}.mid'))
        except Exception as e:
            print(f'Error converting {song}: {e}')
            continue


def main():
    parser = argparse.ArgumentParser(description='Extract Deemo songs to midi files.')
    # Either --single, --check, or --extract must be specified
    group = parser.add_mutually_exclusive_group(required=True)
    # Single takes 2 arguments: the path to the Deemo song json file and the path to the output midi file
    group.add_argument('--single', nargs=2, metavar=('song_path', 'output_path'),
                       help='Extract a single Deemo song to a midi file.')
    # Check takes 1 argument: the path to the directory containing the Deemo songs
    group.add_argument('--check', nargs=1, metavar='songs_dir',
                       help='A dry run to check if the songs can be extracted to midi files.')
    # Extract takes 3 arguments: the Deemo songs path and the output directory path
    group.add_argument('--extract', nargs=2, metavar=('songs_dir', 'output_dir'),
                       help='Extract all the Deemo songs in the directory to midi files.')
    # One only flag
    parser.add_argument('--one_only', action='store_true', required=False,
                        help='Only convert one difficulty to midi even if '
                             'the notes are not the same when using --extract. '
                             'Uses the difficulty with the most number of notes. '
                             'In case of a tie, any one may be chosen. '
                             'Defaults to False.')
    # Suppress length flag
    parser.add_argument('--suppress_length', action='store_true', required=False,
                        help='Suppress the length mismatch messages when using --check. '
                             'Defaults to False.')
    # Suppress notes flag
    parser.add_argument('--suppress_notes', action='store_true', required=False,
                        help='Suppress the notes mismatch messages when using --check. '
                             'Defaults to False.')
    args = parser.parse_args()

    if args.single:
        deemo_notes = load_json(args.single[0])
        notes = extract_one(deemo_notes)
        midi = list_to_midi(notes)
        midi.save(args.single[1])
    elif args.check:
        _ = check_songs(args.check[0], args.suppress_length, args.suppress_notes)
    elif args.extract:
        extract_songs(args.extract[0], args.extract[1], one_only=args.one_only)
    else:
        raise ValueError('Invalid arguments.')


if __name__ == '__main__':
    main()
