#!/usr/bin/python

import re
import os
import subprocess
import urllib
import xml.etree.ElementTree as xmlElementTree
from math import exp
from time import sleep
from hashlib import md5
from urllib2 import urlopen


def isCodedAA (aa1lettercode):

    return aa1lettercode in 'ACDEFGHIKLMNPQRSTVWY'

# Convertors for amino acid three letter codes <-> one letter codes:
aa123 = {
    'A': 'ALA',  'C': 'CYS',  'D': 'ASP',  'E': 'GLU',  'F': 'PHE',  'G': 'GLY',
    'H': 'HIS',  'I': 'ILE',  'K': 'LYS',  'L': 'LEU',  'M': 'MET',  'N': 'ASN',
    'P': 'PRO',  'Q': 'GLN',  'R': 'ARG',  'S': 'SER',  'T': 'THR',  'V': 'VAL',
    'W': 'TRP',  'Y': 'TYR'
}

aa321 = {}
for onelettercode in aa123.keys():
    aa321[aa123[onelettercode]] = onelettercode

# Wrapper to get one letter codes also from unknown three-letter codes
def get_aa321 (aa):

    aa = aa.upper()
    if aa in aa321:
        return aa321[aa]
    else:
        return 'X'


# returns true if the two lists have at least one matching element.
def overlap (list1,  list2):

    for item in list1:
        if item in list2:
            return True
    return False


# Returns only one sequence from the fasta file, with its id.
# Useful when working with single sequence fastas.
def parseFirstFastaSequence (filename):

    fasta = parseFasta (open (filename, 'r'))

    ID = fasta.keys()[0]

    return (ID,  fasta [ID])


# Converts fasta text to a dictionary of sequences.
def parseFasta (contents):

    cid = None
    d = {}

    for line in contents:
        if line.startswith('>'):
            cid = line[1:].split()[0]
            d[cid] = ''
        else:
            d[cid] += line.strip()

    return d


# Writes dictionary 'd' to fasta format.
def writeFasta(d,  filename):

    f = open(filename,  'w')
    for key in d.keys():
        f.write('>' + key + '\n')

        seq = d[key]

        i = 0
        while i < len(seq):
            j = i + 80
            if j >= len(seq):
                f.write(seq[i:] + '\n')
            else:
                f.write(seq[i:j] + '\n')
            i = j
    f.close()

def downloadPDB (pdbid):

    url= "ftp://ftp.wwpdb.org/pub/pdb/data/structures/divided/pdb/%s/pdb%s.ent.gz" % (pdbid [1:3].lower (), pdbid.lower ())
    p = subprocess.Popen ("/usr/bin/curl %s | /bin/zcat" % url, shell=True, stdout=subprocess.PIPE)
    return p.stdout.read ()

# parseDSSP returns a dictionary.
#
# Example output:
# {
#    'A': [
#            'AFDSCTGERAGAERH..',
#            'CCCCCCHHHHHHHHH..',
#            {
#              'a': [5, 125],
#              'b': [222, 333],
#              ...
#             }
#          ],
#    'B': ...
# }
#
# Meaning:
#
#     data
#      |
#      +--chain A
#      |   |
#      |   +--seq
#      |   |
#      |   +--secstr
#      |   |
#      |   +--disulfid bonds
#      |      |
#      |      +--bond a (pos1, pos2)
#      |      |
#      |      +--bond b (pos1, pos2)
#      |      |
#      |      +-- ...
#      |
#      +--chain B
#          |
#          +-- ...

def parseDSSP (filepath):

    lines = open(filepath,  'r').readlines()

    data = {}
    for line in lines:
        strippedline = line.strip()
        if strippedline.endswith('.') or strippedline.startswith('#'):
            continue

        chain = line[11]
        aa = line[13]
        secstr = line[16]

        if not chain.isalpha():
            continue

        if chain not in data:
            data[chain] = ['', '', {}]

        i = len(data[chain][0])

        if aa.islower():  # disulfid bridge

            if aa not in data[chain][2]:
                data[chain][2][aa] = []
            data [chain][2][aa].append (i)
#           if len( data[ chain ][2][aa] )>2:
#               raise Exception(
#                   'More than 2 cys involved in disulfid ' +
#                   'bridge %s on chain %s in %s'%(aa, chain, filepath))

            aa = 'C'

        data[chain][0] += aa
        data[chain][1] += secstr

    return data

# Parser for HMMER output tables. Not used anymore.
# Ouput format:
# { <hit id> : <score> }
def parseHmmerTblout (tblFile):

    hits = {}
    for line in open (tblFile,  'r'):
        if line.startswith('#'):
            continue # comment

        s = line.split()
        hitID = s[0]
        score = s[5]

        hits[hitID] = score

    return hits


# This works like blast, but uses a hammer database.
# Output format is generated by parseHmmerTblout, no alignments.
# HMMER is not used in hommod anymore
def hmmerscan (querySeq, db):

    queryFile = 'query%i.fasta' % (os.getpid())
    writeFasta({'query': querySeq},  queryFile)

    outFile = 'results%i.tbl' % (os.getpid())
    subprocess.call(['hmmscan',  '--tblout',  outFile,  db,  queryFile])

    if not os.path.isfile(outFile):
        raise Exception("hmmerscan failed")

    hits = parseHmmerTblout(outFile)

    os.remove(queryFile)
    os.remove(outFile)

    return hits


# All sequence ids of a template blast database are expected to have this format.
#   pdb|<pdbid>|<chain id>
templateBlastHitPattern = \
    re.compile (r"^pdb\|[0-9][A-Za-z0-9]{3}\|[A-Za-z0-9]{1,2}$")


# Requests the list of C-alpha numbers, sequence and secondary structure for a yasara chain.
# The three output lists will have the same length.
def getChainCAsSeqSecStr (yasara, obj, chain):

    CAs = []
    seq = ''
    secStr = ''

    atomstring = "atom"
    for s in yasara.ListAtom(
            'CA and obj %i and mol %s and protein' % (obj,  chain),
            'ATOMNUM RESNAME'):
        ss = s.split()
        CAs.append(int(ss[0]))
        seq += get_aa321(ss[1])

        atomstring += ' ' + ss[0]

    for s in yasara.SecStrRes (atomstring):
        secStr += s

    return (CAs,  seq,  secStr)


# A chain in yasara is identified by:
# * the yasara object id, an integer to represent the loaded structure
# * the yasara module that loaded the object
# * the chain identifier
class YasaraChain(object):

    def __init__(self,  yasaramodule,  yasaraobj,  chainID):

        self.obj = yasaraobj
        self.chainID = chainID

        self.yasaramodule = yasaramodule

        # Request these values from yasara at the beginning to 
        # prevent repeated yasara requests from causing delay.

        # The risk of this is that they might not be up to date
        # at the moment of usage!
        self.objname = yasaramodule.ListObj(yasaraobj,  'OBJNAME')[0]

        self.CAs,  self.seq,  self.secstr = \
            getChainCAsSeqSecStr (yasaramodule, yasaraobj, chainID)

    def getTemplateID(self):

        return TemplateID(self.objname,  self.chainID)

    def __repr__(self):
        return "%s-%s" % (self.objname,  self.chainID)

    def getSecStr(self):

        return self.secstr

    def getSequence(self):

        return self.seq

    def __eq__(self,  other):

        if str(self) != str(other):
            return False
        else:
            return self.getSequence() == other.getSequence()

    def __hash__(self):

        return hash((self.objname,  self.chainID,  self.seq))


# This type object holds a pdb accession code and a chain id:
class TemplateID(object):

    def __init__(self,  pdbac,  chainID):

        self.pdbac = pdbac
        self.chainID = chainID

    def __repr__(self):

        return "%s-%s" % (self.pdbac,  self.chainID)

    def __eq__(self,  other):

        if type(other) == str:
            return str(self) == other
        else:
            return self.pdbac.lower() == other.pdbac.lower() and \
                self.chainID == other.chainID

    # Important for comparing two templates:
    def __hash__(self):

        return hash ((self.pdbac,  self.chainID))


# This function assumes a conventional ID format and
# extracts the pdb accession code and chain id from it.
def getTemplatePDBIDandChain (blastHitID):

    if not templateBlastHitPattern.match (blastHitID):
        raise Exception("No template blast hit syntax: \'%s\'" % blastHitID)

    templateID = blastHitID
    if templateID [-2].isupper ():  # AA -> a
        templateID = templateID [:-2] + templateID [-2].lower()

    pdbid = templateID [4:8]
    pdbchain = templateID [-1]

    return pdbid, pdbchain

# Gets the seqres sequence of the template, not the structure's sequence!
def getTemplateSequence (pdbac, chain):

    from flask import current_app as flask_app

    # See if we have a local copy of this sequence, if not
    # then download.
    if flask_app and flask_app.config ['TEMPLATESFASTA'] and \
            os.path.isfile (flask_app.config ['TEMPLATESFASTA']):

        source = open (flask_app.config ['TEMPLATESFASTA'], 'r')
        searchID = "pdb|%s|%s" % (pdbac.upper (), chain)
    else:
        source = urlopen ('ftp://ftp.wwpdb.org/pub/pdb/derived_data/pdb_seqres.txt')
        searchID = '%s_%s' % (pdbac.lower (), chain)

    currentID = None
    currentSeq = ''
    for line in source:

        if line.startswith ('>'):

            if currentID == searchID:
                return currentSeq

            currentID = line [1:].split () [0]
            currentSeq = ''

        elif len (line.strip ()) > 0:

            currentSeq += line.strip ()

    if currentID == searchID:
        return currentSeq
    else:
        return ''

# Returns aligned sequences in a dictionary:
# Not used at the moment!
def parseStockholmAlignment (filename):

    d = {}
    for line in open(filename,  'r').readlines():
        if not line.startswith('#'):

            ac, ali = line.split()

            if ac not in d:
                d[ac] = ''

            d[ac] += ali

    return d

# A single char replacement function for strings:
def replaceCharAt (string, index, newChar):

    return string[: index] + newChar + string[index + 1:]

# Extends secondary structure (secstr) where two ranges of
# 'elementType' (example: helix/strand) of length 'elementLength' or longer
# are interrupted by one occurence of a different type (mostly random coil)
# by replacing this single occurence by 'elementType', thus
# making the helix/strand considered uninterrupted in python.
#
# HHHHHH.HHHHHH -> HHHHHHHHHHHHH
#
def removeBulges (secstr, elementType, elementLength):

    surrounding = elementType * elementLength
    i = elementLength
    while (i + elementLength) < len(secstr):

        if secstr[i - elementLength: i] == surrounding and \
                secstr[i + 1: i + 1 + elementLength] == surrounding:

            secstr = replaceCharAt(secstr,  i,  elementType)
            i += elementLength

        i += 1

    return secstr

# returns a list of ranges, telling where deletions start and end.
def identifyDeletedRegions (alignedseq):

    # Place x-es wherever there's a deletion:

    #'ASFGASHDF....GSARRAEYT...'
    #              ||
    #              \/
    #'         xxxx         xxx'

    deletions = ''
    for i in range (len (alignedseq)):
        if alignedseq[i].isalpha():
            deletions += ' '
        else:
            deletions += 'x'

            if i > 0 and deletions[i-1] != 'x':
                j = max(0, i-3)
                if 'x' in deletions[j:i]:
                    deletions = deletions[:j+1] + 'x' * (i-j)

    # convert 'x'-es to ranges,  ignore the terminal 'x'-es.

    #'     xxxxxx     xx     xxxx'
    #              ||
    #              \/
    #      5 --- 11  16-18

    ranges = []
    i = 0
    while i < len(deletions):
        i = deletions.find('x', i)
        if i == -1:
            break

        f = deletions.find(' ', i)
        if f == -1:
            break

        if i > 0:
            ranges.append([i, f])
        i = f+1

    return ranges


# Coverage: % of the sequence that is aligned
# Identity: % of aligned residues that matches the other sequence's residue
def getCoverageIdentity(alignedSeqFrom, alignedSeqTo):

    nalign, pid = getNalignIdentity(alignedSeqFrom, alignedSeqTo)
    pcov = (100*nalign)/len(alignedSeqFrom.replace('-', ''))

    return [pcov, pid]

# Returns #aligned residue & Identity
def getNalignIdentity(alignedseq1, alignedseq2):

    nid = 0
    nalign = 0
    for i in range(len(alignedseq1)):
        if alignedseq1[i].isalpha() and alignedseq2[i].isalpha():
            nalign += 1
            if alignedseq1[i].upper() == alignedseq2[i].upper():
                nid += 1
    if nalign > 0:
        return [nalign,  (100.0 * nid) / nalign]
    else:
        return [0, 0.0]

# Returns just the Identity
def getPercentageIdentity (alignedseq1, alignedseq2):

    nalign, pid = getNalignIdentity (alignedseq1, alignedseq2)

    return pid

# Returns just the number of aligned residues
def getNResiduesAligned (alignedseq1, alignedseq2):
    nalign = 0
    for i in range (len (alignedseq1)):

        aa1 = alignedseq1[i].upper()
        aa2 = alignedseq2[i].upper()

        if aa1.isalpha() and aa2.isalpha():
            nalign += 1

    return nalign

# alias
getSequenceIdentity = getPercentageIdentity

# Removes the sequences shorter than 'minLength'
def filterMinLength (minlength, sequenceDictionary):

    r = {}
    for key in sequenceDictionary.keys():
        if len (sequenceDictionary[key]) >= minlength:
            r [key] = sequenceDictionary [key]

    return r


# Removes all gap chars ('-', '.') from sequence.
def seqWithoutGaps(seq):
    s = ''
    for i in range(len(seq)):
        if seq[i].isalpha():
            s += seq[i]
    return s


# Determines which of the loops in loopsDict fits the deletion best
# and returns its key in loopsDict.
# This function simply looks at how well the length of the loop
# matches the length of the deletion.
def selectBestReplacementLoop (lenDeletion, loopsDict):
    bestAC = None
    bestLooplen = 0
    for ac in loopsDict:
        looplen = len (seqWithoutGaps (loopsDict [ac]))

        if not bestAC or \
           abs(looplen - lenDeletion) < abs(bestLooplen - lenDeletion):
            bestAC = ac
            bestLooplen = looplen

    return bestAC


# Generates an unique id for a given sequence.
def idForSeq(seq):
    h = md5(seq).hexdigest()

    return h[:8]+'-'+h[8:12]+'-'+h[12:16]+'-'+h[16:20]+'-'+h[20:]

# Gets the pdbreport text for a pdb entry:
def getPDBReportEntry (pdbid):
    url = 'ftp://ftp.cmbi.ru.nl/pub/molbio/data/pdbreport/%s/%s/pdbout.txt' \
          % (pdbid[1:3], pdbid)
    return urllib.urlopen(url).read()

# Gets the seqres sequences from the rcsb website.
# Don't use this in high frequencies, because the website can't handle it!
def getRCSBSeqs (ac):
    try:
        seqs = {}
        currentChain = None

        url = 'http://www.rcsb.org/pdb/files/fasta.txt?structureIdList=' + ac
        for line in urllib.urlopen (url):
            if line.startswith ('>'):
                currentChain = line.split('|')[0].split(':')[1]
                seqs[currentChain] = ''
            else:
                seqs[currentChain] += line.strip()

        if len(seqs) <= 0:
            raise Exception("No sequences at rcsb entry \'" + ac + "\'")

        return seqs
    except IOError:
        sleep(1)
        return getRCSBSeqs(ac)

# Gets the sequence of an uniprot entry.
# Add -2, -3 after accession code to get splice variants.
def getUniprotSeq (ac):
    try:
        seq = ''
        url = 'http://www.uniprot.org/uniprot/' + ac + '.fasta'
        r = urllib.urlopen(url)
        for line in r.readlines()[1:]:
            seq += line.strip()

        return seq
    except IOError:
        sleep(1)
        return getRCSBSeqs(ac)


# Keeps only blast hits that lie above the output of minIdentity.
def filterGoodHits (hits):

    filtered = {}
    for hitID in hits.keys():
        for alignment in hits[hitID]:
            identity = alignment.getIdentity()
            nalign = alignment.getNumberResiduesAligned()

            if identity > minIdentity(nalign):
                if hitID not in filtered:
                    filtered[hitID] = []
                filtered[hitID].append(alignment)

    return filtered


# http://dx.doi.org/10.1093/protein/12.2.85
# Rost curve, same as in HOPE.
def minIdentity (nalign):

    if nalign <= 0:
        return float('inf')

    n = float (nalign)

    return 480 * pow (n, -0.32 * (1 + exp (-n / 1000)))


# Object to represent the alignment output by blast.
class BlastAlignment(object):


    # In a blast alignment there are two sequences:
    # - a query aligned sequence, that corresponds to the inserted search query.
    # - a subject aligned sequence, that corresponds to the hit that blast found for the query.
    #
    # Blast aligns fragments of sequences so the alignment doesn't neccesarily start at
    # position 1 or end at the final amino acid of the sequence.
    # querystart, queryend, subjectstart & subjectend indicate where in the sequences the alignment starts.

    def __init__(self, querystart, queryend, queryalignment, subjectstart,
                 subjectend, subjectalignment):

        if len(queryalignment) != len(subjectalignment):
            raise Exception("not the same length: %s and %s" % (
                queryalignment, subjectalignment))
        elif len(queryalignment.replace('-', '')) <= 0 or \
                len(subjectalignment.replace('-', '')) <= 0:
            raise Exception("not a single residue aligned")

        self.querystart = querystart
        self.queryend = queryend
        self.queryalignment = queryalignment.upper()

        self.subjectstart = subjectstart
        self.subjectend = subjectend
        self.subjectalignment = subjectalignment.upper()

    # This can be useful for debugging, it's not required for modeling.
    def getMidline(self):
        midline = ''
        for i in range(len(self.queryalignment)):
            if self.queryalignment[i] == self.subjectalignment[i]:
                midline += self.queryalignment[i]
            else:
                midline += ' '
        return midline

    def getNumberResiduesAligned (self):
        n = 0
        for i in range(len(self.queryalignment)):
            if self.queryalignment[i].isalpha() and \
               self.subjectalignment[i].isalpha():
                n += 1
        return n

    # This function returns percentage identity.
    def getIdentity(self):
        n = 0
        nid = 0
        for i in range(len(self.queryalignment)):
            if self.queryalignment[i].isalpha() and \
               self.subjectalignment[i].isalpha() and \
               self.queryalignment[i].upper() != 'X' and \
               self.subjectalignment[i].upper() != 'X':
                n += 1
                if self.queryalignment[i].upper() == \
                        self.subjectalignment[i].upper():
                    nid += 1

        return (100.0 * nid) / n

    def getNumberInsertions(self):
        n = 0
        gapOpen = False
        for i in range(len(self.queryalignment)):
            queryAA = self.queryalignment[i]
            if queryAA.isalpha() and gapOpen:
                gapOpen = False
                n += 1

            if not queryAA.isalpha():
                gapOpen = True

        return n

    # Returns true if 'pos' in query seq is aligned with any alignment in subject seq.
    def covers (self, pos):
        n = self.querystart-1
        for i in range(len(self.queryalignment)):
            if self.queryalignment[i].isalpha():

                if n == pos:
                    return self.subjectalignment[i].isalpha()
                n += 1
        return False

    # Get single amino acid 1-letter code.
    def getQueryAA(self, pos):
        n = self.querystart-1
        for i in range(len(self.queryalignment)):
            if self.queryalignment[i].isalpha():

                if n == pos:
                    return self.queryalignment[i]
                n += 1

        return '-'

    # Get single amino acid 1-letter code.
    def getSubjectAA(self, pos):
        n = self.querystart-1
        for i in range(len(self.queryalignment)):
            if self.queryalignment[i].isalpha():

                if n == pos:
                    return self.subjectalignment[i]
                n += 1

        return '-'

# Parses the xml output of blastp and converts it to
# BlastAlignment objects, output like so:
# {
#   hit_id1: [
#       alignment1,
#       alignment2
#   ],
#   hit_id2: [
#       alignment3,
#       alignment4
#   ]
# }
def parseBlastXML(xmlstring):
    if len(xmlstring) == 0:
        raise Exception('empty xml string')

    hits = {}

    root = xmlElementTree.fromstring(xmlstring)

    iterations = root.find('BlastOutput_iterations')
    for it in iterations.findall('Iteration'):
        for mem in it.findall('Iteration_hits'):
            for hit in mem.findall('Hit'):

                hitID = hit.find('Hit_def').text
                hits[hitID] = []

                hsps = hit.find('Hit_hsps')
                for hsp in hsps.findall('Hsp'):
                    querystart = int(hsp.find('Hsp_query-from').text)
                    queryend = int(hsp.find('Hsp_query-to').text)
                    queryali = hsp.find('Hsp_qseq').text

                    subjstart = int(hsp.find('Hsp_hit-from').text)
                    subjend = int(hsp.find('Hsp_hit-to').text)
                    subjali = hsp.find('Hsp_hseq').text

                    hits[hitID].append(BlastAlignment(querystart, queryend,
                                       queryali, subjstart, subjend, subjali))
    return hits


# Syntax in blastp text output, not used anymore:
queryp = re.compile(r'Query\s*\ = \s*[0-9a-z\-]+')
lengthp = re.compile(r'Length\s*\ = \s*\d+')

# Parses plain text output of blastp, not used anymore.
def parseBlastResults(lines):
    if len(lines) <= 0:
        return {}

    i = 0
    while not queryp.match(lines[i].strip()):
        i += 1
        if i >= len(lines) or lines[i].endswith('>'):
            raise Exception("Query not found")

    # queryID = lines[i].split('=')[1].strip()

    while not lengthp.match(lines[i]):
        i += 1
        if i >= len(lines) or lines[i].endswith('>'):
            raise Exception("Length indication not found")
    querylength = int(lines[i].split('=')[1])

    hits = {}
    while not lines[i].startswith('>'):
        i += 1
        if i >= len(lines):  # No hits
            return hits

    while i < len(lines):
        hitID = lines[i][1:].split()[0]
        if hitID.startswith('lcl|'):
            hitID = hitID[4:]

        i += 1

        alis = []

        querystart = 0
        subjectstart = 0
        queryend = 0
        subjectend = 0

        queryali = ""
        subjectali = ""

        while i < len(lines) and not lines[i].startswith('>'):
            if lines[i].startswith('Query'):
                s = lines[i].split()
                if len(s) == 4:
                    if len(queryali) <= 0:
                        querystart = int(s[1])
                    queryend = int(s[3])

                    queryali += s[2]
                elif len(s) == 2 and len(queryali) > 0:
                    queryali += s[1]
                else:
                    raise Exception("Unexpected format: " + lines[i])
            elif lines[i].startswith('Sbjct'):
                s = lines[i].split()
                if len(s) == 4:
                    if len(subjectali) <= 0:
                        subjectstart = int(s[1])
                    subjectend = int(s[3])

                    subjectali += s[2]
                elif len(s) == 2 and len(subjectali) > 0:
                    subjectali += s[1]
                else:
                    raise Exception("Unexpected format: " + lines[i])
            elif 'Score' in lines[i] and len(queryali) > 0:
                if len(queryali.replace('-', '')) > querylength:
                    msg = "query alignment too long for" + \
                          "{} (max {} aa): {}".format(hitID, querylength,
                                                      queryali)
                    raise Exception(msg)

                alis.append(BlastAlignment(querystart, queryend, queryali,
                                           subjectstart, subjectend,
                                           subjectali))

                queryali = ""
                subjectali = ""

            i += 1

        if len(queryali.replace('-', '')) > querylength:
            msg = "Query alignment too long for {} (max {} aa): {}".format(
                hitID, querylength, queryali)
            raise Exception(msg)

        alis.append(BlastAlignment(querystart, queryend, queryali, subjectstart,
                                   subjectend, subjectali))

        hits[hitID] = alis

    return hits
