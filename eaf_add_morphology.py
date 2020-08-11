import os
import re
import json
import html
from lxml import etree


EAF_TIME_MULTIPLIER = 1000  # time stamps are in milliseconds


class EafProcessor:
    """
    Contains methods for adding morphological analysis from a Tsakorpus
    JSON file to the source ELAN file.
    """
    rxDir = re.compile('[/\\\\][^/\\\\]+$')
    rxSpeakerCode = re.compile('^\\[[^\\[\\]]+\\]$')

    def __init__(self, tiers, lang='',
                 wordType='words', lemmaType='lemma',
                 grammType='gramm', partsType='morph',
                 glossType='gloss',
                 lexTiers=None,
                 grammTiers=None):
        self.eafTree = None
        self.jsonDoc = None
        self.lang = lang
        self.wordType = wordType
        self.lemmaType = lemmaType
        self.grammType = grammType
        self.partsType = partsType
        self.glossType = glossType
        self.addLexTiers = []      # Additional tiers, children of lemma tier
        if lexTiers is not None:
            self.addLexTiers = lexTiers
        self.addGrammTiers = []    # Additional tiers, children of gramm tier
        if grammTiers is not None:
            self.addGrammTiers = grammTiers
        if not tiers.startswith('^'):
            tiers = '^' + tiers
        if not tiers.endswith('$'):
            tiers += '$'
        self.rxTiers = re.compile(tiers)    # regex for names or types of tiers to be analyzed
        self.lastID = 0
        self.settings = self.load_settings()

    def load_settings(self):
        """
        Load tsakorpus settings from a JSON file (needed for ordering
        grammatical tags correctly).
        """
        fnameIn = 'conf/corpus.json'
        if not os.path.exists(fnameIn):
            print('conf/corpus.json not found; grammatical tags ordeing can be chaotic.')
            return {}
        settings = {}
        with open(fnameIn, 'r', encoding='utf-8') as fIn:
            settings = json.load(fIn)
        return settings

    def get_tlis(self, srcTree):
        """
        Retrieve and return all time labels from the XML tree.
        """
        tlis = {}
        iTli = 0
        for tli in srcTree.xpath('/ANNOTATION_DOCUMENT/TIME_ORDER/TIME_SLOT'):
            timeValue = ''
            if 'TIME_VALUE' in tli.attrib:
                timeValue = tli.attrib['TIME_VALUE']
            tlis[tli.attrib['TIME_SLOT_ID']] = {
                'n': iTli,
                'time': float(timeValue) / EAF_TIME_MULTIPLIER
            }
            iTli += 1
        return tlis

    def write_analyses(self, fnameEafOut):
        """
        Write current (analyzed) EAF tree to the output file.
        """
        if self.eafTree is None:
            return
        with open(fnameEafOut, 'w', encoding='utf-8', newline='\n') as fOut:
            fOut.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            text = str(etree.tostring(self.eafTree, pretty_print=True, encoding='unicode'))
            text = text.replace('</TIER><TIER', '</TIER>\n\t<TIER')
            fOut.write(text)

    def clean_segments(self, segments):
        """
        Remove text that is not going to be present in the ELAN file,
        e.g. speaker marks at the beginning of the turn, which are added
        automatically during ELAN -> JSON conversion.
        """
        for s in segments:
            if len(s['words']) <= 0:
                continue
            s['text'] = s['text'].strip()
            while len(s['words']) > 0 and len(s['words'][0]['wf'].strip()) <= 0:
                del s['words'][0]
            if len(s['words']) <= 0:
                continue
            firstWord = s['words'][0]
            if (firstWord['wtype'] != 'word'
                    and EafProcessor.rxSpeakerCode.search(firstWord['wf']) is not None
                    and s['text'].startswith(firstWord['wf'])):
                s['text'] = s['text'][len(firstWord['wf']):].strip()
                del s['words'][0]

    def collect_analyzed_segments(self):
        """
        Collect all time-aligned segments from the JSON object. For
        each segment, store the analyses of its words in a dictionary.
        """
        analyzedSegments = []
        # Sentences are sorted by their start time.
        for s in self.jsonDoc['sentences']:
            if 'lang' not in s or s['lang'] != 0:
                continue
            if 'src_alignment' not in s or 'words' not in s:
                continue
            for sa in s['src_alignment']:
                offStart = sa['off_start_sent']
                offEnd = sa['off_end_sent']
                curSegment = {
                    'start_time': sa['true_off_start_src'],
                    'words': [],
                    'text': s['text'][offStart:offEnd]
                }
                for word in s['words']:
                    wOffStart = word['off_start']
                    wOffEnd = word['off_end']
                    if wOffStart >= offStart and wOffEnd <= offEnd:
                        curSegment['words'].append(word)
                if len(curSegment['words']) > 0:
                    analyzedSegments.append(curSegment)
        self.clean_segments(analyzedSegments)
        return analyzedSegments

    def create_dependent_annotation(self, curID, parentID, prevID, text):
        """
        Create an XML element representing one annotation in analysis tiers.
        """
        if prevID == '':
            annoTxt = '<ANNOTATION>\n\t\t\t<REF_ANNOTATION ANNOTATION_ID="' + curID \
                      + '" ANNOTATION_REF="' + parentID + '">\n'
        else:
            annoTxt = '<ANNOTATION>\n\t\t\t<REF_ANNOTATION ANNOTATION_ID="' + curID \
                      + '" ANNOTATION_REF="' + parentID + '" PREVIOUS_ANNOTATION="' + prevID + '">\n'
        annoTxt += '\t\t\t\t<ANNOTATION_VALUE>' + html.escape(text) \
                   + '</ANNOTATION_VALUE>\n\t\t\t</REF_ANNOTATION>\n\t\t</ANNOTATION>'
        return etree.XML(annoTxt)

    def group_ana(self, word):
        """
        Group word's analyses by lemma and return them
        in a dictionary.
        """
        anaByLemma = {}
        if 'ana' not in word:
            return anaByLemma
        for ana in word['ana']:
            if type(ana['lex']) == list:
                lex = '/'.join(ana['lex'])
            else:
                lex = ana['lex']
            if lex not in anaByLemma:
                anaByLemma[lex] = [ana]
            else:
                anaByLemma[lex].append(ana)
        return anaByLemma

    def parse_ana(self, ana):
        """
        Retrieve grammatical tags and glosses from a JSON analysis.
        """
        def key_comp(p):
            if ('lang_props' not in self.settings
                    or self.lang not in self.settings['lang_props']
                    or 'gr_fields_order' not in self.settings['lang_props'][self.lang]):
                return -1
            if p[0] not in self.settings['lang_props'][self.lang]['gr_fields_order']:
                if p[0].lower() == 'pos':
                    return -2
                return len(self.settings['lang_props'][self.lang]['gr_fields_order'])
            return self.settings['lang_props'][self.lang]['gr_fields_order'].index(p[0])

        gramm = ''
        parts = ana['parts']
        gloss = ana['gloss']
        grValues = []
        for field in sorted(ana):
            if not field.startswith('gr.'):
                continue
            value = ana[field]
            if type(value) == list:
                value = ', '.join(value)
            grValues.append((field[3:], value))
        for fv in sorted(grValues, key=key_comp):
            if len(gramm) > 0:
                gramm += ', '
            gramm += fv[1]
        return gramm, parts, gloss

    def process_segment(self, segID, words, wordTier, lemmaTier, grammTier,
                        partsTier, glossTier, addLexTiers, addGrammTiers):
        """
        Add analyses for one segment.
        """
        prevWordID = ''
        for word in words:
            curWordID = 'a' + str(self.lastID)
            self.lastID += 1
            wordEl = self.create_dependent_annotation(curWordID, segID, prevWordID, word['wf'])
            prevWordID = curWordID
            wordTier.insert(-1, wordEl)
            if word['wtype'] != 'word':
                continue
            anaByLemma = self.group_ana(word)
            prevLemmaID = ''
            for lemma in sorted(anaByLemma):
                curLemmaID = 'a' + str(self.lastID)
                self.lastID += 1
                lemmaEl = self.create_dependent_annotation(curLemmaID, curWordID, prevLemmaID, lemma)
                prevLemmaID = curLemmaID
                lemmaTier.insert(-1, lemmaEl)
                prevGrammID = ''
                for addLexTier in addLexTiers:
                    # It is assumed that the value of addLexTier is the same
                    # for all analyses with the given lemma
                    if addLexTier in anaByLemma[lemma][0]:
                        curAddID = 'a' + str(self.lastID)
                        self.lastID += 1
                        value = anaByLemma[lemma][0][addLexTier]
                        if type(value) == list:
                            value = '/'.join(value)
                        addEl = self.create_dependent_annotation(curAddID, curLemmaID, '', value)
                        addLexTiers[addLexTier].insert(-1, addEl)
                for ana in anaByLemma[lemma]:
                    curGrammID = 'a' + str(self.lastID)
                    self.lastID += 1
                    curPartsID = 'a' + str(self.lastID)
                    self.lastID += 1
                    curGlossID = 'a' + str(self.lastID)
                    self.lastID += 1
                    gramm, parts, gloss = self.parse_ana(ana)
                    grammEl = self.create_dependent_annotation(curGrammID, curLemmaID, prevGrammID, gramm)
                    partsEl = self.create_dependent_annotation(curPartsID, curGrammID, '', parts)
                    glossEl = self.create_dependent_annotation(curGlossID, curPartsID, '', gloss)
                    prevGrammID = curGrammID
                    grammTier.insert(-1, grammEl)
                    partsTier.insert(-1, partsEl)
                    glossTier.insert(-1, glossEl)
                    for addGrammTier in addGrammTiers:
                        if addGrammTier in ana:
                            curAddID = 'a' + str(self.lastID)
                            self.lastID += 1
                            value = ana[addGrammTier]
                            if type(value) == list:
                                value = '/'.join(value)
                            addEl = self.create_dependent_annotation(curAddID, curGrammID, '', value)
                            addGrammTiers[addGrammTier].insert(-1, addEl)

    def process_tier(self, tierNode, participant, analyzedSegments):
        """
        Add tokenization and analyses to one transcription tier.
        """
        nTokens = 0
        nWords = 0
        nAnalyzed = 0
        iCurAnaSegment = 0
        tierID = tierNode.attrib['TIER_ID']
        wordTier, lemmaTier, grammTier, partsTier, glossTier, addLexTiers, addGrammTiers = self.get_analysis_tiers(tierNode, participant)

        for segNode in tierNode.xpath('ANNOTATION/ALIGNABLE_ANNOTATION'):
            if iCurAnaSegment >= len(analyzedSegments):
                continue
            if 'ANNOTATION_ID' not in segNode.attrib:
                continue
            aID = segNode.attrib['ANNOTATION_ID']
            try:
                segText = segNode.xpath('ANNOTATION_VALUE')[0].text.strip().lower()
            except AttributeError:
                continue
            tli1 = segNode.attrib['TIME_SLOT_REF1']
            startTime = self.tlis[tli1]['time']
            while not (analyzedSegments[iCurAnaSegment]['text'].strip().lower() == segText
                       and startTime - 0.1 <= analyzedSegments[iCurAnaSegment]['start_time'] <= startTime + 0.1):
                iCurAnaSegment += 1
                if iCurAnaSegment >= len(analyzedSegments):
                    break
            if iCurAnaSegment >= len(analyzedSegments):
                continue
            words = analyzedSegments[iCurAnaSegment]['words']
            nTokens += len(words)
            nWords += sum(1 for word in words if word['wtype'] == 'word')
            nAnalyzed += sum(1 for word in words
                             if word['wtype'] == 'word'
                             and 'ana' in word
                             and len(word['ana']) > 0
                             and any(len(ana) > 0 for ana in word['ana']))
            self.process_segment(aID, words,
                                 wordTier, lemmaTier, grammTier, partsTier, glossTier,
                                 addLexTiers, addGrammTiers)

        return nTokens, nWords, nAnalyzed

    def get_analysis_tiers(self, tierNode, participant):
        """
        Check if empty analysis tiers are already present for
        the given participant. If not, add them.
        Return tier nodes for all analysis tiers.
        """
        tierID = tierNode.attrib['TIER_ID']
        tierParent = tierNode.getparent()

        wordTiers = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.wordType + '\''
                                       ' and @PARENT_REF=\'' + tierID + '\']')
        if len(wordTiers) <= 0:
            wordTierTxt = '<TIER LINGUISTIC_TYPE_REF="' + self.wordType +\
                          '" PARENT_REF="' + tierID + '" PARTICIPANT="' + participant +\
                          '" TIER_ID="Words@' + participant + '"/>\n'
            tierParent.insert(tierParent.index(tierNode) + 1, etree.XML(wordTierTxt))
        wordTier = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.wordType + '\''
                                      ' and @PARENT_REF=\'' + tierID + '\']')[0]
        wordTierID = wordTier.attrib['TIER_ID']

        lemmaTiers = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.lemmaType + '\''
                                        ' and @PARENT_REF=\'' + wordTierID + '\']')
        if len(lemmaTiers) <= 0:
            lemmaTierTxt = '<TIER LINGUISTIC_TYPE_REF="' + self.lemmaType + \
                           '" PARENT_REF="' + wordTierID + '" PARTICIPANT="' + participant + \
                           '" TIER_ID="Lemma@' + participant + '"/>\n'
            tierParent.insert(tierParent.index(wordTier) + 1, etree.XML(lemmaTierTxt))
        lemmaTier = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.lemmaType + '\''
                                       ' and @PARENT_REF=\'' + wordTierID + '\']')[0]
        lemmaTierID = lemmaTier.attrib['TIER_ID']

        addLexTiers = {}    # tier type -> tier node
        for addLexTierName in sorted(self.addLexTiers, reverse=True):
            addTierTxt = '<TIER LINGUISTIC_TYPE_REF="' + addLexTierName + \
                         '" PARENT_REF="' + lemmaTierID + '" PARTICIPANT="' + participant + \
                         '" TIER_ID="' + addLexTierName + '@' + participant + '"/>\n'
            tierParent.insert(tierParent.index(lemmaTier) + 1, etree.XML(addTierTxt))
            addLexTier = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + addLexTierName + '\''
                                            ' and @PARENT_REF=\'' + lemmaTierID + '\']')[0]
            addLexTiers[addLexTierName] = addLexTier

        grammTiers = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.grammType + '\''
                                        ' and @PARENT_REF=\'' + lemmaTierID + '\']')
        if len(grammTiers) <= 0:
            grammTierTxt = '<TIER LINGUISTIC_TYPE_REF="' + self.grammType + \
                           '" PARENT_REF="' + lemmaTierID + '" PARTICIPANT="' + participant + \
                           '" TIER_ID="Gramm@' + participant + '"/>\n'
            tierParent.insert(tierParent.index(lemmaTier) + 1, etree.XML(grammTierTxt))
        grammTier = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.grammType + '\''
                                       ' and @PARENT_REF=\'' + lemmaTierID + '\']')[0]
        grammTierID = grammTier.attrib['TIER_ID']

        partsTiers = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.partsType + '\''
                                        ' and @PARENT_REF=\'' + grammTierID + '\']')
        if len(partsTiers) <= 0:
            partsTierTxt = '<TIER LINGUISTIC_TYPE_REF="' + self.partsType + \
                           '" PARENT_REF="' + grammTierID + '" PARTICIPANT="' + participant + \
                           '" TIER_ID="Morph@' + participant + '"/>\n'
            tierParent.insert(tierParent.index(grammTier) + 1, etree.XML(partsTierTxt))
        partsTier = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.partsType + '\''
                                       ' and @PARENT_REF=\'' + grammTierID + '\']')[0]
        partsTierID = partsTier.attrib['TIER_ID']

        glossTiers = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.glossType + '\''
                                        ' and @PARENT_REF=\'' + partsTierID + '\']')
        if len(glossTiers) <= 0:
            glossTierTxt = '<TIER LINGUISTIC_TYPE_REF="' + self.glossType + \
                           '" PARENT_REF="' + partsTierID + '" PARTICIPANT="' + participant + \
                           '" TIER_ID="Gloss@' + participant + '"/>\n'
            tierParent.insert(tierParent.index(partsTier) + 1, etree.XML(glossTierTxt))
        glossTier = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.glossType + '\''
                                       ' and @PARENT_REF=\'' + partsTierID + '\']')[0]

        addGrammTiers = {}  # tier type -> tier node
        for addGrammTierName in sorted(self.addGrammTiers, reverse=True):
            addTierTxt = '<TIER LINGUISTIC_TYPE_REF="' + addGrammTierName + \
                         '" PARENT_REF="' + grammTierID + '" PARTICIPANT="' + participant + \
                         '" TIER_ID="' + addGrammTierName + '@' + participant + '"/>\n'
            tierParent.insert(tierParent.index(grammTier) + 1, etree.XML(addTierTxt))
            addGrammTier = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + addGrammTierName + '\''
                                              ' and @PARENT_REF=\'' + grammTierID + '\']')[0]
            addGrammTiers[addGrammTierName] = addGrammTier

        return wordTier, lemmaTier, grammTier, partsTier, glossTier, addLexTiers, addGrammTiers

    def check_tier_types(self):
        """
        Check if ELAN tier types needed for the morphological annotation
        already exist in the ELAN file. If not, add them.
        """
        tierAttrs = [
            ('Symbolic_Subdivision', self.wordType),
            ('Symbolic_Subdivision', self.lemmaType),
            ('Symbolic_Subdivision', self.grammType),
            ('Symbolic_Association', self.partsType),
            ('Symbolic_Association', self.glossType)
        ]
        for addLexTier in self.addLexTiers:
            tierAttrs.append(('Symbolic_Association', addLexTier))
        for addGrammTier in self.addGrammTiers:
            tierAttrs.append(('Symbolic_Association', addGrammTier))
        for constraint, tierType in tierAttrs:
            tierTypeTxt = '<LINGUISTIC_TYPE CONSTRAINTS="' + constraint + '"' \
                          ' GRAPHIC_REFERENCES="false" LINGUISTIC_TYPE_ID="' + tierType + '"' \
                          ' TIME_ALIGNABLE="false"/>\n'
            tierEl = self.eafTree.xpath('/ANNOTATION_DOCUMENT/LINGUISTIC_TYPE[@LINGUISTIC_TYPE_ID=\'' + tierType + '\']')
            lastTier = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER')[-1]
            tierParent = lastTier.getparent()
            if len(tierEl) <= 0:
                tierParent.insert(tierParent.index(lastTier) + 1, etree.XML(tierTypeTxt))

    def add_analyses(self):
        """
        Add analyses from self.jsonDoc to self.eafTree.
        """
        nTokens = 0
        nWords = 0
        nAnalyzed = 0
        analyzedSegments = self.collect_analyzed_segments()
        self.tlis = self.get_tlis(self.eafTree)
        self.check_tier_types()
        participantID = 1
        for tierNode in self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER'):
            if 'TIER_ID' not in tierNode.attrib:
                continue
            tierID = tierNode.attrib['TIER_ID']
            if (self.rxTiers.search(tierID) is not None
                    or self.rxTiers.search(tierNode.attrib['LINGUISTIC_TYPE_REF']) is not None):
                if 'PARTICIPANT' not in tierNode.attrib:
                    participant = ''
                else:
                    participant = tierNode.attrib['PARTICIPANT']
                if len(participant) <= 0:
                    participant = 'SP' + str(participantID)
                    participantID += 1
                curTokens, curWords, curAnalyzed = self.process_tier(tierNode, participant, analyzedSegments)
                nTokens += curTokens
                nWords += curWords
                nAnalyzed += curAnalyzed
        self.eafTree.xpath('/ANNOTATION_DOCUMENT/HEADER/'
                           'PROPERTY[@NAME=\'lastUsedAnnotationId\']')[0].text = str(self.lastID - 1)
        return nTokens, nWords, nAnalyzed

    def process_corpus(self):
        if not os.path.exists('eaf'):
            print('All ELAN files should be located in the eaf folder.')
            return
        if not os.path.exists('json'):
            print('All Tsakorpus JSON files should be located in the json folder.')
            return
        if not os.path.exists('eaf_analyzed'):
            os.makedirs('eaf_analyzed')

        nTokens = 0
        nWords = 0
        nAnalyzed = 0
        nDocs = 0

        for root, dirs, files in os.walk('eaf'):
            for fname in files:
                if not fname.lower().endswith('.eaf'):
                    continue
                fnameEaf = os.path.join(root, fname)
                fnameJson = 'json' + fnameEaf[3:len(fnameEaf)-3] + 'json'
                fnameEafOut = 'eaf_analyzed' + fnameEaf[3:]
                if not os.path.exists(fnameJson):
                    print('No JSON found for ' + fnameEaf + '.')
                    continue
                self.eafTree = etree.parse(fnameEaf)
                with open(fnameJson, 'r', encoding='utf-8') as fJson:
                    self.jsonDoc = json.load(fJson)
                if (len(self.jsonDoc) <= 0 or 'sentences' not in self.jsonDoc
                        or len(self.jsonDoc['sentences']) <= 0):
                    print('JSON for ' + fnameEaf + ' is empty.')
                    continue
                outDirName = EafProcessor.rxDir.sub('', fnameEafOut)
                if len(outDirName) > 0 and not os.path.exists(outDirName):
                    os.makedirs(outDirName)
                nDocs += 1
                self.lastID = int(self.eafTree.xpath('/ANNOTATION_DOCUMENT/HEADER/'
                                                     'PROPERTY[@NAME=\'lastUsedAnnotationId\']')[0].text) + 1
                curTokens, curWords, curAnalyzed = self.add_analyses()
                nTokens += curTokens
                nWords += curWords
                nAnalyzed += curAnalyzed
                self.write_analyses(fnameEafOut)
        if nWords == 0:
            percentAnalyzed = 0
        else:
            percentAnalyzed = round(nAnalyzed / nWords * 100, 2)
        print(str(nDocs) + ' documents processed.')
        print(str(nTokens) + ' tokens, ' + str(nWords) + ' words, '
              + str(nAnalyzed) + ' analyzed (' + str(percentAnalyzed) + '%).')


if __name__ == '__main__':
    # ep = EafProcessor('.*_Transcription-txt-.*', lang='meadow_mari')
    ep = EafProcessor('tx@.*', lang='adyghe',
                      grammTiers=['trans_ru', 'lex2', 'trans_ru2'])
    ep.process_corpus()
