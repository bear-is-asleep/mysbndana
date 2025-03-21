from sbnd.general import utils
from pyanalib import panda_helpers
from .particlegroup import ParticleGroup
from sbnd.detector.volume import *
from sbnd.constants import *


class CAFSlice(ParticleGroup):
    """
    CAF Slice class. Has functions for slc level (no pfps)
    
    Args:
        CAF : CAF dataframe with useful functions
    """
    #-------------------- constructor/rep --------------------#
    def __init__(self,data,**kwargs):
      super().__init__(data,**kwargs)
    def __getitem__(self, item):
      data = super().__getitem__(item)
      return CAFSlice(data
                      ,prism_bins=self.prism_binning
                      ,pot=self.pot)
    def copy(self,deep=True):
      return CAFSlice(self.data.copy(deep),pot=self.pot,prism_bins=self.prism_binning)
    def load(fname,key='slice',**kwargs):
      df = pd.read_hdf(fname,key=key,**kwargs)
      return CAFSlice(df,**kwargs)
    #-------------------- cutters --------------------#
    def cut_is_cont(self,cut=True):
      """
      Cut to only contained
      """
      condition = self.data.best_muon.cont_tpc
      self.apply_cut('cut.cont', condition, cut=cut)
    def cut_has_nuscore(self,cut=True):
      """
      Cut those that don't have a nu score. They didn't get any reco
      """
      condition = self.data.nu_score >= 0
      self.apply_cut('cut.has_nuscore', condition, cut)
    
    def cut_cosmic(self,crumbs_score=None,fmatch_score=None,nu_score=None,use_opt0=False,cut=False,use_isclearcosmic=True):
      """
      Cut to only cosmic tracks
      """
      print(f'Number of clear cosmic: {len(self.data[self.data.is_clear_cosmic == 1])}')
      if use_isclearcosmic:
        print('Cutting is clear cosmic')
        condition = self.data.is_clear_cosmic != 1
      else:
        print('Skipping is clear cosmic cut')
        condition = np.array([True]*len(self.data))
      if crumbs_score is not None:
          print(f'Cutting crumbs score: {crumbs_score}')
          condition &= self.data.crumbs_result.bestscore > crumbs_score
      if fmatch_score is not None:
          if use_opt0:
              print(f'Cutting opt0 score: {fmatch_score}')
              condition &= self.data.opt0.score > fmatch_score
          elif use_opt0 == 'highlevel':
              print(f'Cutting highlevel opt0 score: {fmatch_score} (R-H/R)')
              # R - H / R
              _score = (self.data.opt0.measPE - self.data.opt0.hypoPE)/self.data.opt0.measPE
              condition &= _score > fmatch_score    
          
          else:
              print(f'Cutting fmatch score: {fmatch_score}')
              condition &= self.data.fmatch.score < fmatch_score
      if nu_score is not None:
          print(f'Cutting nu score: {nu_score}')
          condition &= self.data.nu_score > nu_score

      self.apply_cut('cut.cosmic', condition, cut)
    def cut_fv(self,volume=FV,cut=False):
      """
      Cut to only in fv
      """
      keys = [
        'cut.fv',
        'truth.fv' #truth fv but not really a cut
      ]
      conditions = [
        involume(self.data.vertex, volume=volume), #based on pandora vertex
        involume(self.data.truth.position,volume=volume) #based on true vertex
      ]
      self.apply_cut(keys[0], conditions[0], cut)
      self.apply_cut(keys[1], conditions[1], False) #Do not cut on true vertex
    def cut_muon(self,cut=False):
      """
      Cut to only muon
      """
      condition = self.data.has_muon
      self.apply_cut('cut.muon', condition, cut)
    def cut_trk(self,cut=False):
      """
      Cut to only tracks
      """
      condition = self.data.has_trk
      self.apply_cut('cut.trk', condition, cut)
    def cut_all(self,cut=False):
      """
      add a column that is true if all cuts are true
      """
      condition = self.data.cut.fv\
        & self.data.cut.cosmic\
        & self.data.cut.trk\
        & self.data.cut.muon
      self.apply_cut('cut.all', condition, cut)
    #-------------------- adders --------------------#
    def add_has_muon(self,pfp):
      """
      Check if there is a muon
      """
      # Set keys, conditions and values
      keys = ['has_muon']
      #Get slices with muons
      muons = pfp.data[pfp.data.bestpdg == 13]
      inds = utils.get_sub_inds_from_inds(muons.index.values,self.data.index.values,self.index_depth)
      #Set condition
      condition = pd.Series(False,index=self.data.index)
      condition.loc[inds] = True
      self.add_cols(keys,[True],conditions=condition,fill=False)
    def add_has_trk(self,pfp):
      """
      Check if there is a track
      """
      # Set keys, conditions and values
      keys = [
        'has_trk',
        'best_trk_score'
      ]
      #Get slices with tracks
      trks = pfp.data[pfp.data.semantic_type == 0]
      inds = utils.get_sub_inds_from_inds(trks.index.values,self.data.index.values,self.index_depth)
      #Set condition
      condition = pd.Series(False,index=self.data.index)
      condition.loc[inds] = True
      #Set values
      best_trk_score = pfp.data.groupby(level=[0,1,2]).trackScore.max()
      is_trk = pd.Series(True,index=self.data.index).values
      values = [
        True,
        best_trk_score
      ]
      #Handle adding columns of differing types
      self.add_cols([keys[0]],[values[0]],conditions=condition,fill=False)
      self.add_cols([keys[1]],[values[1]],conditions=condition,fill=np.nan)
    def add_in_av(self):
      """
      Add containment 1 or 0 for each pfp
      """
      #Set keys, values, conditions
      keys = [
        'truth.av',
        'vertex.av'
      ]
      values = [
        involume(self.data.truth.position,volume=AV),
        involume(self.data.vertex,volume=AV)
      ]
      self.add_cols(keys,values,fill=False)
    def add_shws_trks(self,pfp,energy_threshold=0.):
      """
      Count the number of showers and tracks
      energy_threshold: minimum energy to be observable (this probably needs some extra thinking)
      """
      #Get slice indices in common
      inds = utils.get_sub_inds_from_inds(pfp.data.index.values,self.data.index.values,self.index_depth)
      
      #Find number of showers and tracks per slice
      trk_counts = (pfp.data.semantic_type == 0).groupby(level=[0,1,2]).sum()
      shw_counts = (pfp.data.semantic_type == 1).groupby(level=[0,1,2]).sum()
      
      #Find true number of showers and tracks per slice
      observable = (pfp.data.trk.truth.p.startE-pfp.data.trk.truth.p.endE) >= energy_threshold
      true_trk_counts = ((abs(pfp.data.trk.truth.p.pdg) == 13) & observable).groupby(level=[0,1,2]).sum()\
                  + ((abs(pfp.data.trk.truth.p.pdg) == 211) & observable).groupby(level=[0,1,2]).sum()\
                  + ((abs(pfp.data.trk.truth.p.pdg) == 321) & observable).groupby(level=[0,1,2]).sum()\
                  + ((abs(pfp.data.trk.truth.p.pdg) == 2212) & observable).groupby(level=[0,1,2]).sum()
      true_shw_counts = ((abs(pfp.data.trk.truth.p.pdg) == 11) & observable).groupby(level=[0,1,2]).sum()\
                  + ((abs(pfp.data.trk.truth.p.pdg) == 22) & observable).groupby(level=[0,1,2]).sum()\
                  + 2*((abs(pfp.data.trk.truth.p.pdg) == 111) & observable).groupby(level=[0,1,2]).sum()
      
      #Add to slice
      keys = [
        'nshw',
        'ntrk',
        'npfp',
        'truth.nshw',
        'truth.ntrk',
        'truth.npfp'
      ]
      self.add_key(keys)
      cols = panda_helpers.getcolumns(keys,depth=self.key_length())
      self.data.loc[:,cols[0]] = shw_counts
      self.data.loc[:,cols[1]] = trk_counts
      self.data.loc[:,cols[2]] = shw_counts + trk_counts
      self.data.loc[inds,cols[3]] = true_shw_counts
      self.data.loc[inds,cols[4]] = true_trk_counts
      self.data.loc[inds,cols[5]] = true_shw_counts + true_trk_counts
      
    def add_pdg_counts(self,pfp):
      """
      Count the number of each type of particle by pdg
      """
      #Find number of each pdg per slice
      reco = pfp.data.bestpdg.groupby(level=[0,1,2]).value_counts().unstack()
      reco = reco.fillna(0)
      reco.columns = [f'reco.pdg_{i:.0f}' for i in reco.columns]
      inds = reco.index.values
      
      #Add to slice
      keys = list(reco.columns)
      self.add_key(keys,fill=0)
      cols = panda_helpers.getcolumns(keys,depth=self.key_length())
      self.data.loc[inds,cols] = reco.values
      
      #Find true number of each pdg per slice
      true = abs(pfp.data.trk.truth.p.pdg).groupby(level=[0,1,2]).value_counts().unstack()
      true = true.fillna(0)
      true.columns = [f'truth.pdg_{i:.0f}' for i in true.columns]
      inds = true.index.values
      
      #Add to slice
      keys = list(true.columns)
      self.add_key(keys,fill=0)
      cols = panda_helpers.getcolumns(keys,depth=self.key_length())
      self.data.loc[inds,cols] = true.values
    
    def add_tot_visE(self):
      """
      Find total visible energy
      """
      # Set keys, values, conditions
      keys = [
        "truth.visE"
      ]
      visible = np.max([self.data.truth.plane.I0.I0.visE.values
        ,self.data.truth.plane.I0.I1.visE.values
        ,self.data.truth.plane.I0.I2.visE.values],axis=0)
      
      self.add_cols(keys,[visible]) 
    
    def add_event_type(self):
      """
      Add event type from genie type map. True event type
      """
      iscc = self.data.truth.iscc == 1
      isnumu = self.data.truth.pdg == 14
      isanumu = self.data.truth.pdg == -14
      isnue = self.data.truth.pdg == 12
      isanue = self.data.truth.pdg == -12
      iscosmic = self.data.truth.pdg == -1 #masked to 1
      istrueav = self.data.truth.av #filled to bool
      
      #aggregate true types
      isnumuccav = iscc & (isnumu | isanumu) & istrueav & ~iscosmic #numu cc av
      isnueccav = iscc & (isnue | isanue) & istrueav & ~iscosmic #nue cc av
      isncav = ~iscc & istrueav & ~iscosmic #nc av
      iscosmicav = istrueav & iscosmic #cosmic av
      isdirt = ~istrueav & ~iscosmic #dirt
      
      #Consider adding exclusive channels??
      
      #Add to slice
      keys = [
        'truth.event_type'
      ]
      self.add_key(keys,fill=-1)
      cols = panda_helpers.getcolumns(keys,depth=self.key_length())
      self.data.loc[isnumuccav,cols[0]] = 0 #numu cc
      self.data.loc[isncav,cols[0]] = 1 #nc
      self.data.loc[isnueccav,cols[0]] = 2 #nue cc
      self.data.loc[iscosmic,cols[0]] = 3 #cosmic
      self.data.loc[isdirt,cols[0]] = 4 #dirt
      #the rest are unknown
    
    def add_best_muon(self,pfp,get_best_muon=True,method='energy'):
      """
      Add the best muon to the slice
      """
      #Get the best muon if requested
      if get_best_muon:
        pfp = pfp.get_best_muon(method=method)
      #Get slice indices in common
      inds = utils.get_sub_inds_from_inds(pfp.data.index.values,self.data.index.values,self.index_depth)
      
      #Add to slice - float values
      keys = [
        'best_muon.energy',
        'best_muon.p',
        'best_muon.theta',
        'best_muon.costheta',
        'best_muon.dir.x',
        'best_muon.dir.y',
        'best_muon.dir.z',
        'best_muon.len',
        'best_muon.start.x',
        'best_muon.start.y',
        'best_muon.start.z',
        'best_muon.end.x',
        'best_muon.end.y',
        'best_muon.end.z',
        'best_muon.truth.p.pdg',
        'best_muon.truth.p.startE',
        'best_muon.truth.p.endE',
        'best_muon.truth.p.start.x',
        'best_muon.truth.p.start.y',
        'best_muon.truth.p.start.z',
        'best_muon.truth.p.end.x',
        'best_muon.truth.p.end.y',
        'best_muon.truth.p.end.z',
        'best_muon.truth.p.start_process',
        'best_muon.truth.p.end_process',
        'best_muon.truth.p.theta',
        'best_muon.truth.p.costheta',
        'best_muon.truth.p.genp.x',
        'best_muon.truth.p.genp.y',
        'best_muon.truth.p.genp.z',
        'best_muon.truth.p.genp.tot',
        'best_muon.prism_theta',
        'best_muon.truth.p.prism_theta',
        'best_muon.dazzle.muonScore',
        'best_muon.dazzle.pionScore',
        'best_muon.dazzle.protonScore',
        'best_muon.dazzle.pdg',
        'best_muon.truth.p.mass',
        'best_muon.truth.p.genE',
      ]
      self.add_key(keys)
      cols = panda_helpers.getcolumns(keys,depth=self.key_length())
      
      #add the best muon to the slice
      self.data.loc[inds,cols[0]] = pfp.data.trk.bestenergy
      self.data.loc[inds,cols[1]] = pfp.data.trk.bestmom
      self.data.loc[inds,cols[2]] = pfp.data.trk.theta
      self.data.loc[inds,cols[3]] = np.cos(pfp.data.trk.theta)
      self.data.loc[inds,cols[4]] = pfp.data.trk.dir.x
      self.data.loc[inds,cols[5]] = pfp.data.trk.dir.y
      self.data.loc[inds,cols[6]] = pfp.data.trk.dir.z
      self.data.loc[inds,cols[7]] = pfp.data.trk.len
      self.data.loc[inds,cols[8]] = pfp.data.trk.start.x
      self.data.loc[inds,cols[9]] = pfp.data.trk.start.y
      self.data.loc[inds,cols[10]] = pfp.data.trk.start.z
      self.data.loc[inds,cols[11]] = pfp.data.trk.end.x
      self.data.loc[inds,cols[12]] = pfp.data.trk.end.y
      self.data.loc[inds,cols[13]] = pfp.data.trk.end.z
      self.data.loc[inds,cols[14]] = pfp.data.trk.truth.p.pdg
      self.data.loc[inds,cols[15]] = pfp.data.trk.truth.p.startE
      self.data.loc[inds,cols[16]] = pfp.data.trk.truth.p.endE
      self.data.loc[inds,cols[17]] = pfp.data.trk.truth.p.start.x
      self.data.loc[inds,cols[18]] = pfp.data.trk.truth.p.start.y
      self.data.loc[inds,cols[19]] = pfp.data.trk.truth.p.start.z
      self.data.loc[inds,cols[20]] = pfp.data.trk.truth.p.end.x
      self.data.loc[inds,cols[21]] = pfp.data.trk.truth.p.end.y
      self.data.loc[inds,cols[22]] = pfp.data.trk.truth.p.end.z
      self.data.loc[inds,cols[23]] = pfp.data.trk.truth.p.start_process
      self.data.loc[inds,cols[24]] = pfp.data.trk.truth.p.end_process
      self.data.loc[inds,cols[25]] = pfp.data.trk.truth.p.theta
      self.data.loc[inds,cols[26]] = np.cos(pfp.data.trk.truth.p.theta)
      self.data.loc[inds,cols[27]] = pfp.data.trk.truth.p.genp.x
      self.data.loc[inds,cols[28]] = pfp.data.trk.truth.p.genp.y
      self.data.loc[inds,cols[29]] = pfp.data.trk.truth.p.genp.z
      self.data.loc[inds,cols[30]] = np.sqrt(np.sum(pfp.data.trk.truth.p.genp**2,axis=1))
      self.data.loc[inds,cols[31]] = pfp.data.trk.prism_theta #prism theta
      self.data.loc[inds,cols[32]] = pfp.data.trk.truth.p.prism_theta #prism theta 
      self.data.loc[inds,cols[33]] = pfp.data.trk.dazzle.muonScore
      self.data.loc[inds,cols[34]] = pfp.data.trk.dazzle.pionScore
      self.data.loc[inds,cols[35]] = pfp.data.trk.dazzle.protonScore
      self.data.loc[inds,cols[36]] = pfp.data.trk.dazzle.pdg
      self.data.loc[inds,cols[37]] = abs(pfp.data.trk.truth.p.pdg).map(PDG_TO_MASS_MAP)
      self.data.loc[inds,cols[38]] = pfp.data.trk.truth.p.genE
      
      #Add to slice - bool values
      keys = [
        'best_muon.cont_tpc',
        'best_muon.truth.p.cont_tpc'
      ]
      self.add_key(keys,fill=False)
      cols = panda_helpers.getcolumns(keys,depth=self.key_length())
      self.data.loc[inds,cols[0]] = pfp.data.trk.cont_tpc
      self.data.loc[inds,cols[1]] = pfp.data.trk.truth.p.cont_tpc
    #-------------------- getters --------------------#
    #-------------------- plotters --------------------#
      
       
       
        
      
      
      
      
  