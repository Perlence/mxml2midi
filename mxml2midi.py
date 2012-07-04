from __future__ import division
import pdb
import re
from lxml.etree import ElementTree, Element, XPath
from midiutil.MidiFile import MIDIFile, Events

def getpitch(note):
    pitches = {'C':0, 'D':2, 'E':4, 'F':5, 'G':7, 'A':9, 'B':11}
    accs = {'':0, '#':1, 'b':-1}
    pattern = r'([CDEFGAB]{1})([#b]?)(-?\d{1})'
    note, accidental, octave = re.match(pattern, note).group(1, 2, 3)
    result = (int(octave) + 1) * 12 + pitches[note] + accs[accidental]
    return result

def getduration(name):
    names = ['whole', 'half', 'quarter', 'eighth', '16th', '32th',  '64th', '128th', '256th']
    values = [2 ** (2 - i) for i, _ in enumerate(names)]
    return dict(zip(names, values))[name]

def getdynamic(name):
    names = ['ppp', 'pp', 'p', 'mp', 'mf', 'f', 'ff', 'fff']
    values = [16 * i - 1 for i, _ in enumerate(names, 1)]
    return dict(zip(names, values))[name]

def gettext(node, src='text', default=''):
    return getattr(node, src) if node != None else default

def getint(node, src='text', default=0):
    return int(getattr(node, src)) if node != None else default

def handle_score(score):
    parts = score.findall('part-list/score-part')
    midiparts = []
    for part in parts:
        actualpart = score.find('part[@id="%s"]' % part.get('id'))
        tuning = handle_tuning(actualpart)
        trackname = gettext(part.find('part-name'))
        midipart = MIDIFile(1)
        midipart.addTrackName(0, 0, trackname)
        midipart.name = trackname
        for channel, _ in enumerate(tuning):
            midipart.addProgramChange(0, channel, 0, getint(part.find('.//midi-program')))
        midipart.addTempo(0, 0, 120)
        handle_measures(midipart, actualpart, tuning)
        midiparts.append(midipart)
    return midiparts

def handle_tuning(part):
    strings = part.findall('.//staff-tuning')
    result = []
    for string in strings:
        step = gettext(string.find('tuning-step'))
        octave = gettext(string.find('tuning-octave'))
        alter = getint(string.find('tuning-alter'))
        note = getpitch(step + octave) + alter
        result.append(note)
    return result

def handle_measures(midi, part, tuning):
    time = 0
    beats, beat_type = 4, 4
    ties = Element('ties')
    for measure in part.findall('measure'):
        beats = getint(measure.find('attributes/time/beats'), default=beats)
        beat_type = getint(measure.find('attributes/time/beat-type'), default=beat_type)
        notes = measure.findall('note')
        for note in notes:
            if getint(note.find('voice')) == 1:
                actualnotes = getint(note.find('time-modification/actual-notes'), default=1)
                normalnotes = getint(note.find('time-modification/normal-notes'), default=1)
                duration = (getduration(note.find('type').text) *
                            normalnotes / actualnotes)
                if note.find('dot') != None:
                    duration *= 1.5
                if note.find('chord') != None:
                    time -= duration
                if note.find('notations') != None:
                    dynamic = getdynamic(gettext(note.find('notations/dynamics/*'), 
                                                 src='tag', default='f'))
                    string = getint(note.find('notations/technical/string')) - 1
                    fret = getint(note.find('notations/technical/fret'))
                    pitch = tuning[string] + fret
                    if note.find('tie/[@type="start"]') != None:
                        note.set('time', str(time))
                        note.set('duration', str(duration))
                        ties.append(note)
                    elif note.find('tie/[@type="stop"]') != None:
                        path = ('note[./notations/technical/string[string()="{}"] and ' +
                                './notations/technical/fret[string()="{}"]]').format(string + 1, fret)
                        path = XPath(path)
                        for tie in path(ties):
                            tie_time = float(tie.get('time'))
                            tie_duration = float(tie.get('duration')) + duration
                            midi.addNote(0, string, pitch, tie_time, tie_duration, dynamic)
                            ties.remove(tie)
                    elif note.find('grace') != None:
                        steal_time_previous = note.find('grace').get('steal-time-previous')
                        steal_time_previous = int(steal_time_previous.strip('%'))
                        last_note = midi.tracks[0].eventList[-1]
                        duration = last_note.duration * steal_time_previous / 100
                        last_note.duration -= duration
                        time = last_note.time + last_note.duration
                        midi.addNote(0, string, pitch, time, duration, dynamic)
                    else:
                        midi.addNote(0, string, pitch, time, duration, dynamic)
                    time += duration
                elif note.find('rest') != None:
                    time += duration
        if len(notes) == 0:
            time += beats / beat_type * 4

def main():
    import sys
    import os
    import argparse
    
    parser = argparse.ArgumentParser(description='Export MusicXML into multiple MIDI tracks')
    parser.add_argument('input', metavar='INPUT')
    parser.add_argument('--output', '-o', action='store', default=None)
    args = parser.parse_args()
    
    document = ElementTree(file=open(args.input))
    if args.output:
        output = args.output
    else:
        output, _ = os.path.splitext(args.input)
    try:
        os.mkdir(output)
    except OSError:
        pass
    for number, track in enumerate(handle_score(document), 1):
        path = os.path.join(output, '%0*d %s.mid' % (2, number, track.name))
        with open(path, 'wb') as fp:
            track.writeFile(fp)

if __name__ == '__main__':
    main()
