# -*- coding: iso-8859-1 -*- 
from __future__ import division
from decimal import Decimal as dec
import re, numpy as np,itertools as it

def floor(number,decimals):
    '''Proper rounding down.  We have to use decimals to eliminate floating errors'''
    return (dec(int(number*(10**decimals)))/(10**decimals))

class Votes(object):
    '''Information of a single transfer of votes of a particular weight from a parent candidate. 
    Stored as a list inside each receiving candidate object'''
    
    def __init__(self,parentID,weight,voteCount):
        self.parentID=parentID
        self.weight=weight
        self.voteCount=voteCount
        
    def __repr__(self):
        return "Votes(%s x %s = %s from %s)" % (self.voteCount,self.weight,self.voteCount*self.weight,self.parentID)

class Stack(object):
    '''A Stack comtains the estimated prior candidates on ballotsreceived by a candidate by particular weight from multiple sources'''
    
    def __init__(self,maxCandidates,voteCount=0):
        self.priorCandidates=np.zeros(maxCandidates)  # a vector of probable previous candidates on each ballot
        self.voteCount=voteCount
        self.transferredVotes=0
        
    @property
    def orphanVotes(self):
        '''How many votes could not be transferred to a different candidate'''
        return self.voteCount-self.transferredVotes
        
class Candidate(object):       
    def __init__(self,name,maxCandidates=520,voteCount=dec(0)):
        self.maxCandidates=maxCandidates  #laga
        self.name=name
        self.ratio=1
        self.votes=[]
        self.stacks=dict()
        
        if voteCount != dec(0):
            self.stacks[dec(1)]=Stack(maxCandidates,voteCount)   # set up initial stack weight 1 with no priors, only votecount
            self.votes.append(Votes(None,dec(1),voteCount))
            
    def createStack(self,weight):
        if not self.stacks.has_key(weight): self.stacks[weight]=Stack(self.maxCandidates)
        return self.stacks[weight]
    
    def getStacksbyWeight(self,weight):
        """ If the ratio has changed since receiving votes (candidate elected) we need to adjust our query to the new weights"""
        if self.ratio == 1: 
            return [self.stacks[weight]]
        else:
            return [stack for (oldWeight,stack) in self.stacks.items() if floor(oldWeight * self.ratio,5) == weight]
    
    @property
    def voteCount(self):
        return sum([vote.voteCount for vote in self.votes])
            
    @property
    def voteValue(self):
        return sum([vote.voteCount * vote.weight for vote in self.votes])
                        
    @property
    def transferredVotes(self):
        return sum([stack.transferredVotes for stack in self.stacks.values()])
    
    @property
    def orphanVotes(self):
        """ How many ballots ended here and could not be transferred"""
        return self.voteCount-self.transferredVotes
        
    @property
    def orphanVotesValues(self):
        return sum([ (stack.voteCount-stack.transferredVotes) * weight for (weight,stack) in self.stacks.items() ])
               
    @property
    def priorCandidates(self):
        return sum([stack.priorCandidates for stack in self.stacks.values()])
            
    @property
    def firstPlaceVotes(self):
        return sum([vote.voteCount for vote in self.votes if vote.parentID==None])

    def __repr__(self):
        return "<Candidate %s (%s => %s )>" % (self.name,int(self.voteCount),int(self.voteValue))


class Election(object):
    def __init__(self,maxCandidates=500):
        self.candidates=dict()
        self._map=dict()
        self.maxCandidates=maxCandidates
        self.transfers=0    # We like to keep track of total votes transferred to reconcile with number of "priorCandidates"
        
    def addCandidate(self,childID,candidateName,voteCount):
        self.candidates[childID]=Candidate(candidateName,self.maxCandidates,voteCount)
        self._map[childID]=len(self._map)   # assume this candidate maps to the next column of the np.array
        
    def setRatio(self,candidateID,ratio):
        """ Sets a new ratio for the stack weights when candidate is elected """
        self.candidates[candidateID].ratio = ratio
    
    def transferVotes(self,parentID,childID,weight,voteCount):  
        childStack=self.candidates[childID].createStack(weight)    # Get the child stack, or create it if it doesn't exist
        parentStacks=self.candidates[parentID].getStacksbyWeight(weight)   #  Could be multiple stacks that lead to same weight due to rounding
        
        totalParentVotes=sum([stack.voteCount for stack in parentStacks])
        
        for parentStack in parentStacks:
            ratio = parentStack.voteCount/totalParentVotes    # this is the fraction of votes transferred attributed to this particular stack
            parentStack.transferredVotes+=voteCount * ratio 
            childStack.priorCandidates += parentStack.priorCandidates * float((voteCount*ratio) / parentStack.voteCount)
            
        childStack.priorCandidates[self._map[parentID]]+=float(voteCount)  # add the parent candidate to the prior candidates
        childStack.voteCount +=voteCount
        self.candidates[childID].votes.append(Votes(parentID,weight,voteCount))
        
        self.transfers+=voteCount
        
    def commonVotes(self,partyA,partyB):
        """ Shows how many ballots show both the names of Party A and Party B  """
        return self.candidates[partyA].priorCandidates[self._map[partyB]] + self.candidates[partyB].priorCandidates[self._map[partyA]]
        
    def writeCommonCandidates(self,fileName,threshold=0):
        results=list()
        f=open(fileName,"wt")
        for (partyA,partyB) in it.permutations(self.candidates,2):
            commonVotes=self.commonVotes(partyA,partyB)
            if commonVotes > threshold:
                results.append( [partyA,self.candidates[partyA].name,partyB,self.candidates[partyB].name,commonVotes,commonVotes/float(self.candidates[partyA].voteCount),commonVotes/float(self.candidates[partyB].voteCount)])
                f.write("%s;%s;%s;%s;%s;%s;%s\n" % tuple(results[-1]))
        f.close()
        return results
        

    def checksum(self):
      """ A simple check to see if the aggregate of all priorCandidates matches with sum of all vote transfers.  Results should be zero  """
      return float(self.transfers) - sum([sum(stack.priorCandidates*float(stack.orphanVotes/stack.voteCount)) for candidate in election.candidates.values() for stack in candidate.stacks.values()])
          
    def load(self,name):
        f=open(name,"rt")
        parent=None
        
        while True:
            line=f.readline()           
            if not line: break
                
            m=re.match("(?P<candidate>\d{4}) (?P<name>.*) (?P<count>\d{1,1033}.\d{5})",line)
            if m:
                self.addCandidate(m.group("candidate"),m.group("name"),dec(m.group("count")))
                continue
            
            m=re.match("Flutt frá (?P<candidate>\d{4}) .* (?P<count>\d{1,4}) x (?P<weight>\d{1,10}.\d{5})",line)
            if m:   
                if parent !=m.group("candidate"):
                    parent=m.group("candidate")       
                    print "Processing %s" % parent
                continue
            
            m=re.match("Flutt til (?P<candidate>\d{4}) .* (?P<count>\d{1,4}) x (?P<weight>\d{1,10}.\d{5}) = (\d{1,10}.\d{5})",line)
            if m:
                self.transferVotes(parent,m.group("candidate"),dec(m.group("weight")),dec(m.group("count")))
                
            m=re.match("(\d{4}) (.*) KJÖRI.*",line)
            if m:
                parent=m.group(1)
                print "Processing %s" % parent
                while True:
                    line=f.readline()
                    m=re.match("Umframhlutfall frambjóðanda (.*)",line)
                
                    if m:
                        self.setRatio(parent,dec(m.group(1)))
                        break

                    m=re.match("(.*)Úthlutun lokið(.*)",line)
                    if m:
                        break
                        
election=Election(522)
election.load("stv.txt")