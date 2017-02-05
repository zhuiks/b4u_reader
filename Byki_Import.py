# Version: 0.1
#
# This is an Anki add-on for importing Byki b4u files to Anki notes.
# In File->import select Byki files
#
# Based on b4u file reader https://github.com/grantcox/b4u_reader
#
# See github page to report issues or to contribute:
# https://github.com/zhuiks/b4u_reader

import codecs
from datetime import datetime
import os
import struct
import sys

from aqt import mw
from aqt.qt import *
from anki.importing.noteimp import NoteImporter, ForeignNote
import anki.importing as importing
from random import randint

class BykiImporter(NoteImporter):

    def __init__(self, *args):
        NoteImporter.__init__(self, *args)
        self.allowHTML = True
        self.bDeck = None
        self.tagsToAdd = []

    def foreignNotes(self):
        self.open()
        # process all cards
        notes = self.bDeck.getAllCards(self.col.media.dir())
        return notes

    def open(self):
        "Parse the top line and determine the pattern and number of fields."
        # load & look for the right pattern
        self.cacheFile()

    def cacheFile(self):
        "Read file into self.lines if not already there."
        if not self.bDeck:
            self.readFile()

    def readFile(self):
        self.bDeck = Deck(self.file)
        if not self.bDeck.valid:
            raise Exception("unknownFormat")
        self.initMapping()

    def fields(self):
        "Number of fields."
        # self.open()
        return self.bDeck.fieldsCount()

    def getTitle(self):
        self.open()
        return self.bDeck.title

importing.Importers += (("Byki files (*.b4u)", BykiImporter),)

def doBykiImport():
    fileName = QFileDialog.getOpenFileName(mw, 'Select File', "../../../", "Byki Files (*.b4u)")
    bi = BykiImporter(mw.col, fileName)
    # select deck
    did = mw.col.decks.id(bi.getTitle())
    mw.col.decks.select(did)
    # set note type for deck
    m = mw.col.models.byName("Basic")
    deck = mw.col.decks.get(did)
    deck['mid'] = m['id']
    mw.col.decks.save(deck)
    # import into the collection
    bi.initMapping()
    bi.run()


# logfile = codecs.open('log.txt', encoding='utf-8', mode='a')
# def log(s):
#	s = unicode(s)
#	print s.encode('ascii', 'ignore')
#	logfile.write('\n' + s)
# log('---- ' + str(datetime.now()) + ' -----------------')

class Parser(object):
    struct_short = struct.Struct('<H')

    def __init__(self, filename):
        self.filedata = None
        if filename != '':
            try:
                f = open(filename, 'rb')
                self.filedata = f.read()
                f.close()

            except IOError as e:
                pass

    def read(self, fmt, offset):
        if self.filedata is None:
            return None
        read = struct.unpack_from('<' + fmt, self.filedata, offset)
        if len(read) == 1:
            return read[0]
        return read

    def string(self, offset):
        if self.filedata is None:
            return None
        s = u''
        if offset > 0:
            length = self.read('H', offset)
            for i in range(length):
                raw = self.read('H', offset + i * 2 + 2)
                char = raw ^ 0x7E
                s = s + unichr(char)
        return s

    def plain_fixed_string(self, offset):
        if self.filedata is None:
            return None
        plain_bytes = struct.unpack_from('<ssssssssssssssssssssssss', self.filedata, offset)
        plain_string = ''.join(plain_bytes).strip('\0x0')
        return plain_string

    def blob(self, offset, filename=''):
        length = self.read('L', offset)
        data = self.filedata[offset + 8: offset + length + 8]

        return Blob(data, filename)


class Blob(object):
    def __init__(self, data, filename=''):
        self.data = data
        self.filename = filename

    def write(self, filename=None):
        if filename is None:
            filename = self.filename
        if filename is not None and filename != '':
            f = open(filename, 'wb')
            f.write(self.data)
            f.close()


class Card(ForeignNote):
    number = None
    native_title = ''
    native_subtitle = ''
    foreign_title = ''
    foreign_subtitle = ''
    native_alt_answer = ''
    foreign_alt_answer = ''
    foreign_translit = ''
    native_tooltip = ''
    foreign_audio = None
    native_audio = None
    image = None
    fieldsNum = 5

    def __init__(self, parser, data_pointer=0, card_attributes=0):
        ForeignNote.__init__(self)
        self.data = {}
        attributes = [
            ['native_title', 4],
            ['native_subtitle', 8],
            ['foreign_title', 16],
            ['foreign_subtitle', 32],
            ['native_alt_answer', 64],
            ['foreign_alt_answer', 128],
            ['foreign_translit', 256],
            ['native_tooltip', 512],
            ['foreign_audio', 1024],
            ['native_audio', 2048],
            ['image', 4096]
        ]

        self.number = parser.read('L', data_pointer + 4)
        data_pointer = data_pointer + 8
        for attr in attributes:
            if card_attributes & attr[1]:
                data_address = parser.read('L', data_pointer)
                data = None

                if attr[0] == 'foreign_audio':
                    data = parser.blob(data_address)
                elif attr[0] == 'native_audio':
                    data = parser.blob(data_address)
                elif attr[0] == 'image':
                    data = parser.blob(data_address)
                else:
                    data = parser.string(data_address)

                setattr(self, attr[0], data)

                data_pointer = data_pointer + 4

        self.valid = True

    def setFields(self, tofolder, filePrefix):
        def wrap(content, prefix, suffix):
            if content == None or content == '':
                return ''
            return unicode(prefix) + unicode(content) + unicode(suffix)

        cardnum = str(self.number)
        foreign_audio = ''
        native_audio = ''
        image = ''
        if isinstance(self.foreign_audio, Blob):
            fn = filePrefix + cardnum + '_foreign.ogg'
            self.foreign_audio.write(os.path.join(tofolder, fn))
            foreign_audio = u'[sound:%s]' % fn

        if isinstance(self.native_audio, Blob):
            fn = filePrefix + cardnum + '_native.ogg'
            self.native_audio.write(os.path.join(tofolder, fn))
            native_audio = u'[sound:%s]' % fn

        if isinstance(self.image, Blob):
            fn = filePrefix + cardnum + '_image.jpg'
            self.image.write(os.path.join(tofolder, fn))
            image = u'<img src="%s"><br/>' % fn

        self.fields.extend([
            self.foreign_title  + wrap(self.foreign_subtitle, '<br/><p>', '</p>') + wrap(self.foreign_alt_answer, '<br/><p>Also: ', '</p>'),
            image + self.native_title + wrap(self.native_subtitle, '<br/><p>', '</p>') + wrap(self.native_alt_answer, '<br/><p>Also: ', '</p>'),
            foreign_audio,
            native_audio,
            wrap(self.native_tooltip, '<small>', '</small>')
        ])
        return self


class Deck(object):
    title = ''
    description = ''
    native_language = ''
    foreign_language = ''
    copyright = ''
    copyright_url = ''
    creation_date = ''
    app_creator_name = ''
    cardNotes = None

    def __init__(self, filename):
        self.valid = False
        self.cards = []
        self.parser = Parser(filename)
        self.parse()

    def parse(self):
        self.valid = False
        self.data = {}
        self.cards = []

        caret = None
        # find the initial caret position - this changes between files for some reason - search for the "Cards" string
        for i in range(3):
            addr = 104 + i * 4
            if ''.join(self.parser.read('sssss', addr)) == 'Cards':
                caret = addr + 32
                break

        if caret is None:
            return

        deck_details_pointer = self.parser.read('L', 92)
        card_count = self.parser.read('L', caret + 4)
        next_card = self.parser.read('L', caret + 16)

        # read in all of the deck properties - name, creator, description, copyright etc
        fields = {
            'Name': 'title',
            'Side1Lang': 'native_language',
            'Side2Lang': 'foreign_language',
            'Description': 'description',
            'Copyright': 'copyright',
            'CopyrightURL': 'copyright_url',
            'CreationDate': 'creation_date',
            'AppCreatorName': 'app_creator_name'
        }

        while deck_details_pointer != 0:
            detail_label = self.parser.plain_fixed_string(deck_details_pointer + 4)
            if detail_label in fields:
                detail_string = ''
                detail_data = self.parser.read('L', deck_details_pointer + 40)

                if detail_label == 'CreationDate':
                    # not a pointer, this is a timestamp
                    creation_date = datetime.fromtimestamp(detail_data)
                    detail_string = creation_date.strftime('%Y %B %d')
                elif detail_label == 'GUID':
                    detail_string = str(detail_data)
                elif detail_label == 'Ordered':
                    detail_string = str(detail_data)
                else:
                    detail_string = self.parser.string(detail_data)

                # set this property on the Deck object
                setattr(self, fields[detail_label], detail_string)

            # move to the next attribute
            deck_details_pointer = self.parser.read('L', deck_details_pointer)

        self.valid = True

        # read in all of the cards
        while (next_card != 0):
            next_card, card_num, boundary, card_data_pointer, card_attributes = self.parser.read('LLLLL', next_card)
            card = Card(self.parser, card_data_pointer, card_attributes)
            if card.valid:
                self.cards.append(card)

        return self.valid

    def getAllCards(self, tofolder):
        if not self.cardNotes:
            def slugify(value):
                """
                Normalizes string, converts to lowercase, removes non-alpha characters,
                and converts spaces to hyphens.
                """
                import unicodedata
                value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
                value = unicode(re.sub('[^\w\s-]', '', value).strip().lower())
                value = unicode(re.sub('[-\s]+', '-', value))
                return value

            self.cardNotes = []
            prefix = unicode(randint(10,99)) + self.title
            for card in self.cards:
                self.cardNotes.append(card.setFields(tofolder, prefix))
        return self.cardNotes

    def fieldsCount(self):
        return self.cards[0].fieldsNum

#action = QAction("Byki Auto Import...", mw)
#action.triggered.connect(doBykiImport)
#mw.form.menuTools.addAction(action)
