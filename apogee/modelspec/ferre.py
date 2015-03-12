###############################################################################
# ferre.py: module for interacting with Carlos Allende Prieto's FERRE code
###############################################################################
import os, os.path
import copy
import subprocess
import numpy
from functools import wraps
import tempfile
import apogee.tools.path as appath
from apogee.tools import paramIndx,_ELEM_SYMBOL
from apogee.tools.read import modelspecOnApStarWavegrid
import apogee.spec.window as apwindow
import apogee.spec.cannon as cannon
from apogee.modelspec import specFitInput
def paramArrayInputDecorator(startIndx):
    """Decorator to parse spectral input parameters given as arrays,
    assumes the arguments are: something,somethingelse,teff,logg,metals,am,nm,cm,vmicro=,
    startindx is the index in arguments where the teff,logg,... sequence starts"""
    def wrapper(func):
        @wraps(func)
        def scalar_wrapper(*args,**kwargs):
            if numpy.array(args[startIndx]).shape == ():
                newargs= ()
                for ii in range(startIndx):
                    newargs= newargs+(args[ii],)
                for ii in range(6):
                    newargs= newargs+(numpy.array([args[ii+startIndx]]),)
                for ii in range(len(args)-6-startIndx):
                    newargs= newargs+(args[ii+startIndx+6],)
                args= newargs
                if not kwargs.get('vm',None) is None:
                    kwargs['vm']= numpy.array([kwargs['vm']])
            result= func(*args,**kwargs)
            return result
        return scalar_wrapper
    return wrapper

@modelspecOnApStarWavegrid
@paramArrayInputDecorator(0)
def interpolate(teff,logg,metals,am,nm,cm,vm=None,
                lib='GK',pca=True,sixd=True,dr=None,
                offile=None,
                inter=3,f_format=1,f_access=None,
                verbose=False,apStarWavegrid=True):
    """
    NAME:
       interpolate
    PURPOSE:
       Interpolate the model spectral library to give a model spectrum at a desired point
    INPUT:
       Parameters (can be 1D arrays, in this case multiple spectra will be returned):
          teff - Effective temperature (K)
          logg - log10 surface gravity / cm s^-2
          metals - overall metallicity
          am - [alpha/M]
          nm - [N/M]
          cm - [C/M]
          vm= if using the 7D library, also specify the microturbulence
       Library options:
          lib= ('GK') spectral library
          pca= (True) if True, use a PCA compressed library
          sixd= (True) if True, use the 6D library (w/o vm)
          dr= data release
       FERRE options:
          inter= (3) order of the interpolation
          f_format= (1) file format (0=ascii, 1=unf)
          f_access= (None) 0: load whole library, 1: use direct access (for small numbers of interpolations), None: automatically determine a good value (currently, 1)
       Output options:
          apStarWavegrid= (True) if True, output the spectrum onto the apStar wavelength grid, otherwise just give the ASPCAP version (blue+green+red directly concatenated)
          offile= (None) if offile is set, the FERRE OFFILE is saved to this file, otherwise this file is removed
       verbose= (False) if True, run FERRE in verbose mode
    OUTPUT:
       spec[nspec,nwave]
    HISTORY:
       2015-01-23 - Written - Bovy (IAS)
    """
    # Setup temporary directory to run FERRE from
    tmpDir= tempfile.mkdtemp(dir='./')
    try:
        # First write the ipf file with the parameters
        write_ipf(tmpDir,teff,logg,metals,am,nm,cm,vm=vm)
        # Now write the input.nml file
        if f_access is None:
            f_access= 1
        write_input_nml(tmpDir,'input.ipf','output.dat',ndim=7-sixd,
                        nov=0,
                        synthfile=appath.ferreModelLibraryPath\
                            (lib=lib,pca=pca,sixd=sixd,dr=dr,
                             header=True,unf=False),
                        inter=inter,f_format=f_format,
                        f_access=f_access)
        # Run FERRE
        run_ferre(tmpDir,verbose=verbose)
        # Read the output
        out= numpy.loadtxt(os.path.join(tmpDir,'output.dat'))
        if not offile is None:
            os.rename(os.path.join(tmpDir,'output.dat'),offile)
    finally:
        # Clean up
        if os.path.exists(os.path.join(tmpDir,'input.ipf')):
            os.remove(os.path.join(tmpDir,'input.ipf'))
        if os.path.exists(os.path.join(tmpDir,'input.nml')):
            os.remove(os.path.join(tmpDir,'input.nml'))
        if os.path.exists(os.path.join(tmpDir,'output.dat')):
            os.remove(os.path.join(tmpDir,'output.dat'))
        os.rmdir(tmpDir)
    return out

@specFitInput
def fit(spec,specerr,
        teff=4750.,logg=2.5,metals=0.,am=0.,nm=0.,cm=0.,vm=None,
        fixteff=False,fixlogg=False,fixmetals=False,fixam=False,fixcm=False,
        fixnm=False,fixvm=False,
        lib='GK',pca=True,sixd=True,dr=None,
        offile=None,
        inter=3,f_format=1,f_access=None,
        errbar=1,indini=[1,1,1,2,2,3],init=1,initcannon=False,
        verbose=False):
    """
    NAME:
       fit
    PURPOSE:
       Fit a model spectrum to a given data spectrum
    INPUT:
       Either:
          (1) location ID - single or list/array of location IDs
              APOGEE ID - single or list/array of APOGEE IDs; loads aspcapStar
          (2) spec - spectrum: can be (nwave) or (nspec,nwave)
              specerr - spectrum errors: can be (nwave) or (nspec,nwave)
       Input parameters (can be 1D arrays); only used when init=0
          teff= (4750.) Effective temperature (K)
          logg= (2.5) log10 surface gravity / cm s^-2
          metals= (0.) overall metallicity
          am= (0.) [alpha/M]
          nm= (0.) [N/M]
          cm= (0.) [C/M]
          vm= if using the 7D library, also specify the microturbulence
       Fit options:
          fixteff= (False) if True, fix teff at the input value
          fixlogg= (False) if True, fix logg at the input value
          fixmetals= (False) if True, fix metals at the input value
          fixam= (False) if True, fix am at the input value
          fixcm= (False) if True, fix cm at the input value
          fixnm= (False) if True, fix nm at the input value
          fixvm= (False) if True, fix vm at the input value (only if sixd is False)
       Library options:
          lib= ('GK') spectral library
          pca= (True) if True, use a PCA compressed library
          sixd= (True) if True, use the 6D library (w/o vm)
          dr= data release
       FERRE options:
          inter= (3) order of the interpolation
          errbar= (1) method for calculating the error bars
          indini= ([1,1,1,2,2,3]) how to initialize the search (int or array/list with ndim entries)
          init= (1) if 0, initialize the search at the parameters in the pfile
          f_format= (1) file format (0=ascii, 1=unf)
          f_access= (None) 0: load whole library, 1: use direct access (for small numbers of interpolations), None: automatically determine a good value (currently, 1)
       Other options:
          initcannon= (False) If True, initialize a single run by first running the Cannon using the default Cannon fit (sets init=0)
       Output options:
          offile= (None) if offile is set, the FERRE OFFILE is saved to this file, otherwise this file is removed
       verbose= (False) if True, run FERRE in verbose mode
    OUTPUT:
       best-fit parameters (nspec,nparams); in the same order as the FPARAM APOGEE data product
    HISTORY:
       2015-01-29 - Written - Bovy (IAS)
    """
    # Initialize using the Cannon?
    if initcannon:
        init= 0 # just run one fit using the Cannon as a starting guess
        initparams= cannon.polylabels(spec,specerr)
        if not fixteff: teff= initparams[:,0]
        if not fixlogg: logg= initparams[:,1]
        if not fixmetals: metals= initparams[:,2]
        if not fixam: am= initparams[:,3]
        if not fixcm: cm= numpy.zeros_like(initparams[:,0])
        if not fixnm: nm= numpy.zeros_like(initparams[:,0])
    # Make sure the Teff etc. have the right dimensionality
    if len(spec.shape) == 1:
        nspec= 1
    else:
        nspec= spec.shape[0]
    if nspec > 1 and isinstance(teff,float):
        teff= teff*numpy.ones(nspec)
    if nspec > 1 and isinstance(logg,float):
        logg= logg*numpy.ones(nspec)
    if nspec > 1 and isinstance(metals,float):
        metals= metals*numpy.ones(nspec)
    if nspec > 1 and isinstance(am,float):
        am= am*numpy.ones(nspec)
    if nspec > 1 and isinstance(nm,float):
        nm= nm*numpy.ones(nspec)
    if nspec > 1 and isinstance(cm,float):
        cm= cm*numpy.ones(nspec)
    if nspec > 1 and not vm is None and isinstance(vm,float):
        vm= vm*numpy.ones(nspec)
    if dr is None: dr= appath._default_dr()
    # Fix any of the parameters?
    indv= []
    indini= copy.copy(indini) # need to copy bc passed by reference
    if isinstance(indini,numpy.ndarray) and \
            ((not sixd and fixvm) or fixcm or fixnm or fixam or fixmetals \
                 or fixlogg or fixteff):
        indini= list(indini)
    if not sixd and not fixvm:
        indv.append(1)
    elif not sixd:
        if isinstance(indini,list): indini[0]= -1
    if not fixcm:
        indv.append(2-sixd)
    else:
        if isinstance(indini,list): indini[1-sixd]= -1
    if not fixnm:
        indv.append(3-sixd)
    else:
        if isinstance(indini,list): indini[2-sixd]= -1
    if not fixam:
        indv.append(4-sixd)
    else:
        if isinstance(indini,list): indini[3-sixd]= -1
    if not fixmetals:
        indv.append(5-sixd)
    else:
        if isinstance(indini,list): indini[4-sixd]= -1
    if not fixlogg:
        indv.append(6-sixd)
    else:
        if isinstance(indini,list): indini[5-sixd]= -1
    if not fixteff:
        indv.append(7-sixd)
    else:
        if isinstance(indini,list): indini[6-sixd]= -1
    if isinstance(indini,list):
        while -1 in indini: indini.remove(-1)
    # Setup temporary directory to run FERRE from
    tmpDir= tempfile.mkdtemp(dir='./')
    try:
        # First write the ipf file with the parameters
        write_ipf(tmpDir,teff,logg,metals,am,nm,cm,vm=vm)
        # Write the file with the fluxes and the flux errors
        write_ffile(tmpDir,spec,specerr=specerr)
        # Now write the input.nml file
        if f_access is None:
            f_access= 1
        write_input_nml(tmpDir,'input.ipf','output.dat',ndim=7-sixd,
                        nov=7-sixd-fixcm-fixnm-fixam-fixmetals\
                            -fixlogg-fixteff,
                        indv=indv,
                        synthfile=appath.ferreModelLibraryPath\
                            (lib=lib,pca=pca,sixd=sixd,dr=dr,
                             header=True,unf=False),
                        ffile='input.frd',erfile='input.err',
                        opfile='output.opf',
                        inter=inter,f_format=f_format,
                        errbar=errbar,indini=indini,init=init,
                        f_access=f_access)
        # Run FERRE
        run_ferre(tmpDir,verbose=verbose)
        # Read the output
        cols= (1,2,3,4,5,6)
        tmpOut= numpy.loadtxt(os.path.join(tmpDir,'output.opf'),usecols=cols)
        if len(spec.shape) == 1 or spec.shape[0] == 1:
            out= numpy.zeros((1,7))
            tmpOut= numpy.reshape(tmpOut,(1,7-sixd))
        else:
            out= numpy.zeros((nspec,7))
        out[:,paramIndx('TEFF')]= tmpOut[:,-1]
        out[:,paramIndx('LOGG')]= tmpOut[:,-2]
        out[:,paramIndx('METALS')]= tmpOut[:,-3]
        out[:,paramIndx('ALPHA')]= tmpOut[:,-4]
        out[:,paramIndx('N')]= tmpOut[:,-5]
        out[:,paramIndx('C')]= tmpOut[:,-6]
        if sixd and dr == '12':
            out[:,paramIndx('LOG10VDOP')]=\
                numpy.log10(2.478-0.325*out[:,paramIndx('LOGG')])
        else:
            out[:,paramIndx('LOG10VDOP')]= tmpOut[:,0]
        if not offile is None:
            os.rename(os.path.join(tmpDir,'output.dat'),offile)
    finally:
        # Clean up
        if os.path.exists(os.path.join(tmpDir,'input.ipf')):
            os.remove(os.path.join(tmpDir,'input.ipf'))
        if os.path.exists(os.path.join(tmpDir,'input.frd')):
            os.remove(os.path.join(tmpDir,'input.frd'))
        if os.path.exists(os.path.join(tmpDir,'input.err')):
            os.remove(os.path.join(tmpDir,'input.err'))
        if os.path.exists(os.path.join(tmpDir,'input.nml')):
            os.remove(os.path.join(tmpDir,'input.nml'))
        if os.path.exists(os.path.join(tmpDir,'output.dat')):
            os.remove(os.path.join(tmpDir,'output.dat'))
        if os.path.exists(os.path.join(tmpDir,'output.opf')):
            os.remove(os.path.join(tmpDir,'output.opf'))
        os.rmdir(tmpDir)
    return out

@specFitInput
def elemfitall(*args,**kwargs):
    """
    NAME:
       elemfitall
    PURPOSE:
       Fit a model spectrum to a given data spectrum for all element windows
    INPUT:
       Either:
          (1) location ID - single or list/array of location IDs
              APOGEE ID - single or list/array of APOGEE IDs; loads aspcapStar
          (2) spec - spectrum: can be (nwave) or (nspec,nwave)
              specerr - spectrum errors: can be (nwave) or (nspec,nwave)
       Input parameters (can be 1D arrays); only used when init=0
          Either:
             (1) fparam= (None) output of ferre.fit
             (2) teff= (4750.) Effective temperature (K)
                 logg= (2.5) log10 surface gravity / cm s^-2
                 metals= (0.) overall metallicity
                 am= (0.) [alpha/M]
                 nm= (0.) [N/M]
                 cm= (0.) [C/M]
                 vm= if using the 7D library, also specify the microturbulence
       Fit options:
          fixteff= (True) if True, fix teff at the input value
          fixlogg= (True) if True, fix logg at the input value
          fixvm= (True) if True, fix vm at the input value (only if sixd is False)
       The following are set to False based on the element being fit (C -> fixcm=False, N -> fixnm=False, O,Mg,S,Si,Ca,Ti -> fixam=False, rest -> fixmetals=False)
          fixmetals= (None) if True, fix metals at the input value
          fixam= (None) if True, fix am at the input value
          fixcm= (None) if True, fix cm at the input value
          fixnm= (None) if True, fix nm at the input value
       Library options:
          lib= ('GK') spectral library
          pca= (True) if True, use a PCA compressed library
          sixd= (True) if True, use the 6D library (w/o vm)
          dr= data release
       FERRE options:
          inter= (3) order of the interpolation
          errbar= (1) method for calculating the error bars
          indini= ([1,1,1,2,2,3]) how to initialize the search (int or array/list with ndim entries)
          init= (0) if 0, initialize the search at the parameters in the pfile
          f_format= (1) file format (0=ascii, 1=unf)
          f_access= (None) 0: load whole library, 1: use direct access (for small numbers of interpolations), None: automatically determine a good value (currently, 1)
       Output options:
          offile= (None) if offile is set, the FERRE OFFILE is saved to this file, otherwise this file is removed
       verbose= (False) if True, run FERRE in verbose mode
    OUTPUT:
       dictionary with best-fit ELEM_H (nspec)
    HISTORY:
       2015-03-01 - Written - Bovy (IAS)
    """
    # METALS for normalization
    if not kwargs.get('fparam',None) is None:
        metals= kwargs.get('fparam')[:,paramIndx('METALS')]
    else:
        metals= kwargs.get('metals',0.)
    # Run through and fit all elements
    out= {}
    for elem in _ELEM_SYMBOL:
        targs= args+(elem.capitalize(),)
        tefit= elemfit(*targs,**kwargs)
        if elem.lower() == 'c':
            tout= tefit[:,paramIndx('C')]+metals
        elif elem.lower() == 'n':
            tout= tefit[:,paramIndx('N')]+metals
        elif elem.lower() in ['o','mg','s','si','ca','ti']:
            tout= tefit[:,paramIndx('ALPHA')]+metals
        else:
            tout= tefit[:,paramIndx('METALS')]
        out[elem.capitalize()]= tout
    return out

@specFitInput
def elemfit(spec,specerr,elem,
            fparam=None,
            teff=4750.,logg=2.5,metals=0.,am=0.,nm=0.,cm=0.,vm=None,
            fixteff=True,fixlogg=True,fixmetals=None,fixam=None,
            fixcm=None,
            fixnm=None,fixvm=True,
            lib='GK',pca=True,sixd=True,dr=None,
            offile=None,
            inter=3,f_format=1,f_access=None,
            errbar=1,indini=[1,1,1,2,2,3],init=0,
            verbose=False):
    """
    NAME:
       elemfit
    PURPOSE:
       Fit a model spectrum to a given data spectrum for a given element window
    INPUT:
       Either:
          (1) location ID - single or list/array of location IDs
              APOGEE ID - single or list/array of APOGEE IDs; loads aspcapStar
          (2) spec - spectrum: can be (nwave) or (nspec,nwave)
              specerr - spectrum errors: can be (nwave) or (nspec,nwave)
       elem - element to fit (e.g., 'Al')
       Input parameters (can be 1D arrays); only used when init=0
          Either:
             (1) fparam= (None) output of ferre.fit
             (2) teff= (4750.) Effective temperature (K)
                 logg= (2.5) log10 surface gravity / cm s^-2
                 metals= (0.) overall metallicity
                 am= (0.) [alpha/M]
                 nm= (0.) [N/M]
                 cm= (0.) [C/M]
                 vm= if using the 7D library, also specify the microturbulence
       Fit options:
          fixteff= (True) if True, fix teff at the input value
          fixlogg= (True) if True, fix logg at the input value
          fixvm= (True) if True, fix vm at the input value (only if sixd is False)
       The following are set to False based on the element being fit (C -> fixcm=False, N -> fixnm=False, O,Mg,S,Si,Ca,Ti -> fixam=False, rest -> fixmetals=False)
          fixmetals= (None) if True, fix metals at the input value
          fixam= (None) if True, fix am at the input value
          fixcm= (None) if True, fix cm at the input value
          fixnm= (None) if True, fix nm at the input value
       Library options:
          lib= ('GK') spectral library
          pca= (True) if True, use a PCA compressed library
          sixd= (True) if True, use the 6D library (w/o vm)
          dr= data release
       FERRE options:
          inter= (3) order of the interpolation
          errbar= (1) method for calculating the error bars
          indini= ([1,1,1,2,2,3]) how to initialize the search (int or array/list with ndim entries)
          init= (0) if 0, initialize the search at the parameters in the pfile
          f_format= (1) file format (0=ascii, 1=unf)
          f_access= (None) 0: load whole library, 1: use direct access (for small numbers of interpolations), None: automatically determine a good value (currently, 1)
       Output options:
          offile= (None) if offile is set, the FERRE OFFILE is saved to this file, otherwise this file is removed
       verbose= (False) if True, run FERRE in verbose mode
    OUTPUT:
       best-fit parameters (nspec,nparams); in the same order as the FPARAM APOGEE data product (fixed inputs are repeated in the output)
    HISTORY:
       2015-02-27 - Written - Bovy (IAS)
    """
    # Parse fparam
    if not fparam is None:
        teff= fparam[:,paramIndx('TEFF')]
        logg= fparam[:,paramIndx('LOGG')]
        metals= fparam[:,paramIndx('METALS')]
        am= fparam[:,paramIndx('ALPHA')]
        nm= fparam[:,paramIndx('N')]
        cm= fparam[:,paramIndx('C')]
        if sixd:
            vm= None
        else:
            vm= fparam[:,paramIndx('LOG10VDOP')]        
    # Make sure the Teff etc. have the right dimensionality
    if len(spec.shape) == 1:
        nspec= 1
    else:
        nspec= spec.shape[0]
    if nspec > 1 and isinstance(teff,float):
        teff= teff*numpy.ones(nspec)
    if nspec > 1 and isinstance(logg,float):
        logg= logg*numpy.ones(nspec)
    if nspec > 1 and isinstance(metals,float):
        metals= metals*numpy.ones(nspec)
    if nspec > 1 and isinstance(am,float):
        am= am*numpy.ones(nspec)
    if nspec > 1 and isinstance(nm,float):
        nm= nm*numpy.ones(nspec)
    if nspec > 1 and isinstance(cm,float):
        cm= cm*numpy.ones(nspec)
    if nspec > 1 and not vm is None and isinstance(vm,float):
        vm= vm*numpy.ones(nspec)
    if dr is None: dr= appath._default_dr()
    # Set fixXX based on element being fit, first set None to True
    if fixcm is None: fixcm= True
    if fixnm is None: fixnm= True
    if fixam is None: fixam= True
    if fixmetals is None: fixmetals= True
    if elem.lower() == 'c':
        fixcm= False
    elif elem.lower() == 'n':
        fixnm= False
    elif elem.lower() in ['o','mg','s','si','ca','ti']:
        fixam= False
    else:
        fixmetals= False
    # Fix any of the parameters?
    indv= []
    indini= copy.copy(indini) # need to copy bc passed by reference
    if isinstance(indini,numpy.ndarray) and \
            ((not sixd and fixvm) or fixcm or fixnm or fixam or fixmetals \
                 or fixlogg or fixteff):
        indini= list(indini)
    if not sixd and not fixvm:
        indv.append(1)
    elif not sixd:
        if isinstance(indini,list): indini[0]= -1
    if not fixcm:
        indv.append(2-sixd)
    else:
        if isinstance(indini,list): indini[1-sixd]= -1
    if not fixnm:
        indv.append(3-sixd)
    else:
        if isinstance(indini,list): indini[2-sixd]= -1
    if not fixam:
        indv.append(4-sixd)
    else:
        if isinstance(indini,list): indini[3-sixd]= -1
    if not fixmetals:
        indv.append(5-sixd)
    else:
        if isinstance(indini,list): indini[4-sixd]= -1
    if not fixlogg:
        indv.append(6-sixd)
    else:
        if isinstance(indini,list): indini[5-sixd]= -1
    if not fixteff:
        indv.append(7-sixd)
    else:
        if isinstance(indini,list): indini[6-sixd]= -1
    if isinstance(indini,list):
        while -1 in indini: indini.remove(-1)
    if init == 0: indini= 0
    # Setup temporary directory to run FERRE from
    tmpDir= tempfile.mkdtemp(dir='./')
    try:
        # First write the ipf file with the parameters
        write_ipf(tmpDir,teff,logg,metals,am,nm,cm,vm=vm)
        # Write the file with the fluxes and the flux errors
        write_ffile(tmpDir,spec,specerr=specerr)
        # Now write the input.nml file
        if f_access is None:
            f_access= 1
        write_input_nml(tmpDir,'input.ipf','output.dat',ndim=7-sixd,
                        nov=7-sixd-fixcm-fixnm-fixam-fixmetals\
                            -fixlogg-fixteff,
                        indv=indv,
                        synthfile=appath.ferreModelLibraryPath\
                            (lib=lib,pca=pca,sixd=sixd,dr=dr,
                             header=True,unf=False),
                        ffile='input.frd',erfile='input.err',
                        opfile='output.opf',
                        inter=inter,f_format=f_format,
                        errbar=errbar,indini=indini,init=init,
                        f_access=f_access,
                        filterfile=apwindow.path(elem,dr=dr))
        # Run FERRE
        run_ferre(tmpDir,verbose=verbose)
        # Read the output
        cols= (1,2,3,4,5,6)
        tmpOut= numpy.loadtxt(os.path.join(tmpDir,'output.opf'),usecols=cols)
        if len(spec.shape) == 1 or spec.shape[0] == 1:
            out= numpy.zeros((1,7))
            tmpOut= numpy.reshape(tmpOut,(1,7-sixd))
        else:
            out= numpy.zeros((nspec,7))
        out[:,paramIndx('TEFF')]= tmpOut[:,-1]
        out[:,paramIndx('LOGG')]= tmpOut[:,-2]
        out[:,paramIndx('METALS')]= tmpOut[:,-3]
        out[:,paramIndx('ALPHA')]= tmpOut[:,-4]
        out[:,paramIndx('N')]= tmpOut[:,-5]
        out[:,paramIndx('C')]= tmpOut[:,-6]
        if sixd and dr == '12':
            out[:,paramIndx('LOG10VDOP')]=\
                numpy.log10(2.478-0.325*out[:,paramIndx('LOGG')])
        else:
            out[:,paramIndx('LOG10VDOP')]= tmpOut[:,0]
        if not offile is None:
            os.rename(os.path.join(tmpDir,'output.dat'),offile)
    finally:
        # Clean up
        if os.path.exists(os.path.join(tmpDir,'input.ipf')):
            os.remove(os.path.join(tmpDir,'input.ipf'))
        if os.path.exists(os.path.join(tmpDir,'input.frd')):
            os.remove(os.path.join(tmpDir,'input.frd'))
        if os.path.exists(os.path.join(tmpDir,'input.err')):
            os.remove(os.path.join(tmpDir,'input.err'))
        if os.path.exists(os.path.join(tmpDir,'input.nml')):
            os.remove(os.path.join(tmpDir,'input.nml'))
        if os.path.exists(os.path.join(tmpDir,'output.dat')):
            os.remove(os.path.join(tmpDir,'output.dat'))
        if os.path.exists(os.path.join(tmpDir,'output.opf')):
            os.remove(os.path.join(tmpDir,'output.opf'))
        os.rmdir(tmpDir)
    return out

@specFitInput
def elemchi2(spec,specerr,
             elem,elem_linspace=(-0.5,0.5,11),
             fparam=None,
             teff=4750.,logg=2.5,metals=0.,am=0.,nm=0.,cm=0.,vm=None,
             lib='GK',pca=True,sixd=True,dr=None,
             offile=None,
             inter=3,f_format=1,f_access=None,
             verbose=False):
    """
    NAME:
       elemchi2
    PURPOSE:
       Calculate the chi^2 for a given element
    INPUT:
       Either:
          (1) location ID - single or list/array of location IDs
              APOGEE ID - single or list/array of APOGEE IDs; loads aspcapStar
          (2) spec - spectrum: can be (nwave) or (nspec,nwave)
              specerr - spectrum errors: can be (nwave) or (nspec,nwave)
       elem - element to consider (e.g., 'Al')
       elem_linspace= ((-0.5,0.5,11)) numpy.linspace range of abundance, relative to the relevant value in fparam / metals,am,nm,cm
       Input parameters (can be 1D arrays)
          Either:
             (1) fparam= (None) output of ferre.fit
             (2) teff= (4750.) Effective temperature (K)
                 logg= (2.5) log10 surface gravity / cm s^-2
                 metals= (0.) overall metallicity
                 am= (0.) [alpha/M]
                 nm= (0.) [N/M]
                 cm= (0.) [C/M]
                 vm= if using the 7D library, also specify the microturbulence
       Library options:
          lib= ('GK') spectral library
          pca= (True) if True, use a PCA compressed library
          sixd= (True) if True, use the 6D library (w/o vm)
          dr= data release
       FERRE options:
          inter= (3) order of the interpolation
          f_format= (1) file format (0=ascii, 1=unf)
          f_access= (None) 0: load whole library, 1: use direct access (for small numbers of interpolations), None: automatically determine a good value (currently, 1)
       verbose= (False) if True, run FERRE in verbose mode
    OUTPUT:
       chi^2
    HISTORY:
       2015-03-12 - Written - Bovy (IAS)
    """
    # Parse fparam
    if not fparam is None:
        teff= fparam[:,paramIndx('TEFF')]
        logg= fparam[:,paramIndx('LOGG')]
        metals= fparam[:,paramIndx('METALS')]
        am= fparam[:,paramIndx('ALPHA')]
        nm= fparam[:,paramIndx('N')]
        cm= fparam[:,paramIndx('C')]
        if sixd:
            vm= None
        else:
            vm= fparam[:,paramIndx('LOG10VDOP')]        
    # Read the weights
    weights= apwindow.read(elem,apStarWavegrid=False,dr=dr)
    weights/= numpy.sum(weights)
    # Decide which parameter to vary
    nspec= len(teff)
    nvelem= elem_linspace[2]
    var_elem= numpy.tile(numpy.linspace(*elem_linspace),(nspec,1))   
    if elem.lower() == 'c':
        cm= var_elem+numpy.tile(cm,(nvelem,1)).T
    elif elem.lower() == 'n':
        nm= var_elem+numpy.tile(nm,(nvelem,1)).T
    elif elem.lower() in ['o','mg','s','si','ca','ti']:
        am= var_elem+numpy.tile(am,(nvelem,1)).T
    else:
        metals= var_elem+numpy.tile(metals,(nvelem,1)).T
    # Upgrade dimensionality of other parameters for interpolate input
    teff= numpy.tile(teff,(nvelem,1)).T
    logg= numpy.tile(logg,(nvelem,1)).T
    if not sixd:
        vm= numpy.tile(vm,(nvelem,1)).T.flatten()
    if not elem.lower() == 'c':
        cm= numpy.tile(cm,(nvelem,1)).T
    if not elem.lower() == 'n':
        nm= numpy.tile(nm,(nvelem,1)).T
    if not elem.lower() in ['o','mg','s','si','ca','ti']:
        am= numpy.tile(am,(nvelem,1)).T
    if elem.lower() in ['c','n','o','mg','s','si','ca','ti']:
        metals= numpy.tile(metals,(nvelem,1)).T
    # Get interpolated spectra, [nspec,nwave]
    ispec= interpolate(teff.flatten(),logg.flatten(),metals.flatten(),
                       am.flatten(),nm.flatten(),cm.flatten(),vm=vm,
                       lib=lib,pca=pca,sixd=sixd,dr=dr,
                       inter=inter,f_format=f_format,f_access=f_access,
                       verbose=verbose,apStarWavegrid=False)
    dspec= numpy.tile(spec,(1,nvelem)).reshape((nspec*nvelem,spec.shape[1]))
    dspecerr= numpy.tile(specerr,
                         (1,nvelem)).reshape((nspec*nvelem,spec.shape[1]))
    tchi2= _chi2(ispec,dspec,dspecerr,numpy.tile(weights,(nspec*nvelem,1)))
    return numpy.reshape(tchi2,(nspec,nvelem))

def _chi2(mspec,spec,specerr,weights=None):
    """Internal function that calculates the chi^2 for a given model,
     assumes that the wavelength axis==-1"""
    if not weights is None:
        return numpy.sum(weights*(mspec-spec)**2./specerr**2,axis=-1)
    else:
        return numpy.sum((mspec-spec)**2./specerr**2,axis=-1)

def run_ferre(dir,verbose=False):
    """
    NAME:
       run_ferre
    PURPOSE:
       run an instance of FERRE
    INPUT:
       dir - directory to run the instance in (has to have an input.nml file)
       verbose= (False) if True, print the FERRE output
    OUTPUT:
       (none)
    HISTORY:
       2015-01-22 - Written - Bovy (IAS)
    """
    # Set up the subprocess to run FERRE
    if verbose:
        stdout= None
        stderr= None
    else:
        stdout= open('/dev/null', 'w')
        stderr= subprocess.STDOUT
    try:
        subprocess.check_call(['ferre'],cwd=dir,stdout=stdout,stderr=stderr)
    except subprocess.CalledProcessError:
        raise Exception("Running FERRE instance in directory %s failed ..." % dir)
    return None

def write_input_nml(dir,
                    pfile,
                    offile,
                    ffile=None,
                    erfile=None,
                    opfile=None,
                    ndim=6,
                    nov=0,
                    indv=None,
                    synthfile=None,
                    filterfile=None,
                    inter=3,
                    errbar=1,
                    indini=0,
                    init=0,
                    f_format=1,
                    f_access=1):
    """
    NAME:
       write_input_nml
    PURPOSE:
       write a FERRE input.nml file
    INPUT:
       dir - directory where the input.nml file will be written to
       pfile - name of the input parameter file
       offile - name of the output best-fitting model file
       ffile= name of the input parameter file
       erfile= name of the flux errors file
       opfile= name of the output parameter file
       ndim= (6) number of dimensions/parameters
       nov= (0) number of parameters to search (0=interpolation)
       synthfile= (default ferreModelLibraryPath in apogee.tools.path) file name of the model grid's header
       filterfile= (None) name of the file with weights to apply to the chi^2 (as weight x diff/err^2); typically an elemental abundance window
       inter= (3) order of the interpolation
       errbar= (1) method for calculating the error bars
       indini= (0) how to initialize the search
       init= (0) if 0, initialize the search at the parameters in the pfile
       f_format= (1) file format (0=ascii, 1=unf)
       f_access= (1) 0: load whole library, 1: use direct access (for small numbers of interpolations)
    OUTPUT:
       (none; just writes the file)
    HISTORY:
       2015-01-22 - Written - Bovy (IAS)
    """
    if indv is None:
        indv= range(1,nov+1)
    if synthfile is None:
        import apogee.tools.path as appath
        synthfile= appath.ferreModelLibraryPath(header=True)
    with open(os.path.join(dir,'input.nml'),'w') as outfile:
        outfile.write('&LISTA\n')
        outfile.write('NDIM = %i\n' % ndim)
        outfile.write('NOV = %i\n' % nov)
        indvstr= 'INDV ='
        for ii in indv:
            indvstr+= ' %i' % ii
        outfile.write(indvstr+'\n')
        outfile.write("SYNTHFILE(1) = '%s'\n" % synthfile)
        outfile.write("PFILE = '%s'\n" % pfile)
        if not ffile is None:
            outfile.write("FFILE = '%s'\n" % ffile)
        if not erfile is None:
            outfile.write("ERFILE = '%s'\n" % erfile)
        if not opfile is None:
            outfile.write("OPFILE = '%s'\n" % opfile)
        outfile.write("OFFILE = '%s'\n" % offile)
        if not filterfile is None:
            outfile.write("FILTERFILE = '%s'\n" % filterfile)           
        outfile.write('INTER = %i\n' % inter)
        outfile.write('ERRBAR = %i\n' % errbar)
        indinistr= 'INDINI ='
        if isinstance(indini,int):
            indini= numpy.zeros(nov,dtype='int')+indini
        for ii in range(nov):
            indinistr+= ' %i' % indini[ii]
        outfile.write(indinistr+'\n')
        if init == 0:
            outfile.write('NRUNS = 1\n')
        else:
            outfile.write('NRUNS = %i\n' % numpy.prod(indini))
        outfile.write('INIT = %i\n' % init)
        outfile.write('F_FORMAT = %i\n' % f_format)
        outfile.write('F_ACCESS = %i\n' % f_access)
        outfile.write('/\n')
    return None

# Interpolation
@paramArrayInputDecorator(1)
def write_ipf(dir,teff,logg,metals,am,nm,cm,vm=None):
    """
    NAME:
       write_ipf
    PURPOSE:
       write a FERRE input.ipf file
    INPUT:
       dir - directory where the input.ipf file will be written to
       Parameters (can be 1D arrays):
          teff - Effective temperature (K)
          logg - log10 surface gravity / cm s^-2
          metals - overall metallicity
          am - [alpha/M]
          nm - [N/M]
          cm - [C/M]
          vm= if using the 7D library, also specify the microturbulence
    OUTPUT:
       (none; just writes the file)
    HISTORY:
       2015-01-23 - Written - Bovy (IAS)
    """
    with open(os.path.join(dir,'input.ipf'),'w') as outfile:
        for ii in range(len(teff)):
            outStr= 'dummy '
            if not vm is None:
                outStr+= '%.3f ' % numpy.log10(vm[ii])
            outStr+= '%.3f %.3f %.3f %.3f %.3f %.1f\n' \
                % (cm[ii],nm[ii],am[ii],
                   metals[ii],logg[ii],teff[ii])
            outfile.write(outStr)
    return None

# Fitting
def write_ffile(dir,spec,specerr=None):
    """
    NAME:
       write_ffile
    PURPOSE:
       write FERRE input.frd file with input fluxes and input.err with input flux errors
    INPUT:
       dir - directory where the input.frd file will be written to
       spec - spectra (nspec,nwave)
       specerr= (None) if set, aos write the input.err file
    OUTPUT:
       (none; just writes the file)
    HISTORY:
       2015-01-23 - Written - Bovy (IAS)
    """
    if len(spec.shape) == 1: 
        spec= numpy.reshape(spec,(1,len(spec)))
        specerr= numpy.reshape(specerr,(1,len(specerr)))
    numpy.savetxt(os.path.join(dir,'input.frd'),spec)
    if not specerr is None:
        numpy.savetxt(os.path.join(dir,'input.err'),specerr)
    return None
