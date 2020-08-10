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

    def __init__(self, tiers,
                 wordType='words', lemmaType='lemma',
                 grammType='gramm', partsType='parts',
                 glossType='parts'):
        self.eafTree = None
        self.jsonDoc = None
        self.wordType = wordType
        self.lemmaType = lemmaType
        self.grammType = grammType
        self.partsType = partsType
        self.glossType = glossType
        if not tiers.startswith('^'):
            tiers = '^' + tiers
        if not tiers.endswith('$'):
            tiers += '$'
        self.rxTiers = re.compile(tiers)    # regex for names or types of tiers to be analyzed
        self.lastID = 0

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
            fOut.write(str(etree.tostring(self.eafTree, pretty_print=True, encoding='unicode')))

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

    def process_segment(self, aID, words, wordTier):
        """
        Add analyses for one segment.
        """
        prevID = ''
        for word in words:
            curID = 'a' + str(self.lastID)
            self.lastID += 1
            if prevID == '':
                wordTxt = '<ANNOTATION>\n\t\t\t<REF_ANNOTATION ANNOTATION_ID="' + curID \
                          + '" ANNOTATION_REF="' + aID + '">\n'
            else:
                wordTxt = '<ANNOTATION>\n\t\t\t<REF_ANNOTATION ANNOTATION_ID="' + curID \
                          + '" ANNOTATION_REF="' + aID + '" PREVIOUS_ANNOTATION="' + prevID + '">\n'
            wordTxt += '\t\t\t\t<ANNOTATION_VALUE>' + html.escape(word['wf']) \
                       + '</ANNOTATION_VALUE>\n\t\t\t</REF_ANNOTATION>\n\t\t</ANNOTATION>'
            prevID = curID
            wordTier.insert(-1, etree.XML(wordTxt))
            if word['wtype'] != 'word':
                continue

    def process_tier(self, tierNode, analyzedSegments):
        """
        Add tokenization and analyses to one transcription tier.
        """
        nTokens = 0
        nWords = 0
        nAnalyzed = 0
        iCurAnaSegment = 0
        tierID = tierNode.attrib['TIER_ID']
        wordTier = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.wordType + '\''
                                      ' and @PARENT_REF=\'' + tierID + '\']')[0]
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
                # print(analyzedSegments[iCurAnaSegment]['start_time'], '!=', startTime)
                # print(analyzedSegments[iCurAnaSegment]['text'].strip().lower(), '!=', segText)
                iCurAnaSegment += 1
                if iCurAnaSegment >= len(analyzedSegments):
                    break
            if iCurAnaSegment >= len(analyzedSegments):
                continue
            self.process_segment(aID, analyzedSegments[iCurAnaSegment]['words'], wordTier)

        return nTokens, nWords, nAnalyzed

    def check_analysis_tiers(self, tierNode, participant):
        """
        Check if empty analysis tiers are already present for
        the given participant. If not, add them.
        """
        tierID = tierNode.attrib['TIER_ID']
        wordTiers = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER[@LINGUISTIC_TYPE_REF=\'' + self.wordType + '\''
                                       ' and @PARENT_REF=\'' + tierID + '\']')
        if len(wordTiers) <= 0:
            wordTierTxt = '<TIER LINGUISTIC_TYPE_REF="' + self.wordType +\
                          '" PARENT_REF="' + tierID + '" PARTICIPANT="' + participant +\
                          '" TIER_ID="Words@' + participant + '"/>\n'
            tierParent = tierNode.getparent()
            tierParent.insert(tierParent.index(tierNode) + 1, etree.XML(wordTierTxt))

    def check_tier_types(self):
        """
        Check if ELAN tier types needed for the morphological annotation
        already exist in the ELAN file. If not, add them.
        """
        wordTypeTxt = '<LINGUISTIC_TYPE CONSTRAINTS="Symbolic_Subdivision"' \
                      ' GRAPHIC_REFERENCES="false" LINGUISTIC_TYPE_ID="' + self.wordType + '"' \
                      ' TIME_ALIGNABLE="false"/>\n'
        wordConstr = self.eafTree.xpath('/ANNOTATION_DOCUMENT/LINGUISTIC_TYPE[@LINGUISTIC_TYPE_ID=\'' + self.wordType + '\']')
        lastTier = self.eafTree.xpath('/ANNOTATION_DOCUMENT/TIER')[-1]
        tierParent = lastTier.getparent()
        if len(wordConstr) <= 0:
            tierParent.insert(tierParent.index(lastTier) + 1, etree.XML(wordTypeTxt))

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
                participant = tierNode.attrib['PARTICIPANT']
                if len(participant) <= 0:
                    participant = 'SP' + str(participantID)
                    participantID += 1
                self.check_analysis_tiers(tierNode, participant)
                curTokens, curWords, curAnalyzed = self.process_tier(tierNode, analyzedSegments)
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
    ep = EafProcessor('.*_Transcription-txt-.*')
    ep.process_corpus()
