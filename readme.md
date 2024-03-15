# Deemo Extract

Extract Deemo songs into MIDI files.

## Dependencies

- `Python` environment
- `mido` and `tqdm` libraries

Tested on `Python 3.10` with `mido==1.3.0` and `tqdm==4.66.1`.

## Quick Start

This project assumes that you have access to the Deemo song files in the `json` format.

The usage of `extract.py` is as follows:

### `--single`

Extract a single Deemo song to a MIDI file.

```shell
python extract.py --single <song_path> <output_path>
```

Example:

```bash
python extract.py --single /path/to/song.json /path/to/output.mid
```

### `--check`

Perform a dry run to check if each song in the songs directory can be extracted to midi files.

```shell
python extract.py --check <songs_dir>
```

Note that the MIDI extracted from different difficulties of the same song may not be the same. In some cases, the number of notes is not the same. In some other cases, the onset/offset/pitch/velocity of some notes may differ. I call them length mismatch and notes mismatch respectively. These cases can be handled by `extract.py` during the extraction (more details in `--extract`), so the length/notes mismatch messages are more like warnings rather than errors and can be suppressed with the following flags:

`--suppress_length`: Suppress the length mismatch messages.

`--suppress_notes`: Suppress the notes mismatch messages.

Example:

```bash
python extract.py --check /path/to/songs --suppress_length --suppress_notes
```

### `--extract`

Extract all the Deemo songs in the songs directory to midi files.

```bash
python extract.py --extract <songs_dir> <output_dir>
```

By default, when running into either a length mismatch or notes mismatch during the extraction of a song, `extract.py` will convert the song file of each difficulty into a separate MIDI file. This allows you to scrutinize through the results and decide which one you like the most. However, if you don't want to go through this hassle, the following optional flag can help:

`--one_only`: Only convert one difficulty to midi even if the notes are not the same.

If the flag is set, `extract.py` will extract the one with the most number of notes in case of a length mismatch. If there is a tie in length, `extract.py` will randomly choose one to extract. This is because it is found that notes mismatch usually only result in subtle differences. If in doubt, you always have the option to identify the problematic songs using `--check` and manually extract single songs using `--single`.

Example:

```bash
python extract.py --extract /path/to/songs /path/to/output --one_only
```

## References

https://github.com/water-vapor/deemo-to-midi