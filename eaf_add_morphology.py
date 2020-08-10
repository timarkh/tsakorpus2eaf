import os
import re
import json
from lxml import etree


class EafProcessor:
    """
    Contains methods for adding morphological analysis from a Tsakorpus
    JSON file to the source ELAN file.
    """
    rxDir = re.compile('[/\\\\][^/\\\\]+$')

    def __init__(self, tiers):
        self.eafTree = None
        self.jsonDoc = None
        self.rxTiers = tiers    # regexes for names or types of tiers to be analyzed

    def write_analyses(self, fnameEafOut):
        if self.eafTree is None:
            return
        with open(fnameEafOut, 'w', encoding='utf-8', newline='\n') as fOut:
            fOut.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            fOut.write(str(etree.tostring(self.eafTree, pretty_print=True, encoding='unicode')))

    def add_analyses(self, fnameEafOut):
        nTokens = 0
        nWords = 0
        nAnalyzed = 0
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
                curTokens, curWords, curAnalyzed = self.add_analyses(fnameEafOut)
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
