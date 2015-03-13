###############################################################################
# apogee.spec.lsf: Utilities to work with APOGEE LSFs
###############################################################################
from functools import wraps
import math
import numpy
from scipy import special, interpolate
import apogee.tools.read as apread
from apogee.spec.plot import apStarWavegrid
_SQRTTWO= numpy.sqrt(2.)
# Load wavelength solutions
_WAVEPIX_A= apread.apWave('a',ext=2)
_WAVEPIX_B= apread.apWave('b',ext=2)
_WAVEPIX_C= apread.apWave('c',ext=2)
def eval(x,fiber='combo'):
    """
    NAME:
       eval
    PURPOSE:
       evaluate the LSF for a given fiber
    INPUT:
       x - Array of X values for which to compute the LSF (in pixel offset relative to pixel centers; the LSF is calculated at the x offsets for each pixel center)
       fiber= ('combo') fiber number or 'combo' for an average LSF (using zero-based indexing)
    OUTPUT:
       LSF(x|pixel center)
    HISTORY:
       2015-03-12 - Written based on Jon H's code (based on David N's code) - Bovy (IAS)
    """
    # Parse fiber input
    if isinstance(fiber,str) and fiber.lower() == 'combo':
        fiber= [50,100,150,200,250,300]
    elif isinstance(fiber,int):
        fiber= [fiber]
    elif not isinstance(fiber,list) and isinstance(fiber[0],int):
        raise ValueError('fiber input to apogee.spec.lsf.eval not understood ...')
    wav= apStarWavegrid()
    out= numpy.zeros((len(wav),len(x)))
    for chip in ['a','b','c']:
        # Get pixel array for this chip, use fiber[0] for consistency if >1 fib
        pix= wave2pix(wav,chip,fiber[0])
        dx= numpy.roll(pix,-1,)-pix
        dx[-1]= dx[-2]
        xs= numpy.tile(x,(len(wav),1))\
            *numpy.tile(dx,(len(x),1)).T # nwav,nx       
        gd= True-numpy.isnan(pix)
        # Read LSF file for this chip
        lsfpars= apread.apLSF(chip,ext=0)
        # Loop through the fibers
        for fib in fiber:
            out[gd]+= raw(xs[gd],pix[gd],lsfpars[:,300-fib])
    out[out<0.]= 0.
    out/= numpy.tile(numpy.sum(out,axis=1),(len(x),1)).T
    return out

def raw(x,xcenter,params):
    """
    NAME:
       raw
    PURPOSE:
       Evaluate the raw APOGEE LSF (on the native pixel scale)
    INPUT:
       x - Array of X values for which to compute the LSF (in pixel offset relative to xcenter; the LSF is calculated at the x offsets for each xcenter if x is 1D, otherwise x has to be [nxcenter,nx]))
       xcenter - Position of the LSF center (in pixel units)
       lsfarr - the parameter array (from the LSF HDUs in the APOGEE data products)
    OUTPUT:
       LSF(x|xcenter))
    HISTORY:
       2015-02-26 - Written based on Nidever's code in apogeereduce - Bovy (IAS)
    """
    # Parse x
    if len(x.shape) == 1:
        x= numpy.tile(x,(len(xcenter),1))
    # Unpack the LSF parameters
    params= unpack_lsf_params(params)
    # Get the wing parameters at each x
    wingparams= numpy.empty((params['nWpar'],len(xcenter)))
    for ii in range(params['nWpar']):
        poly= numpy.polynomial.Polynomial(params['Wcoefs'][ii])       
        wingparams[ii]= poly(xcenter+params['Xoffset'])
    # Get the GH parameters at each x
    ghparams= numpy.empty((params['Horder']+2,len(xcenter)))
    for ii in range(params['Horder']+2):
        if ii == 1:
            # Fixed, correct for wing
            ghparams[ii]= 1.-wingparams[0]
        else:
            poly= numpy.polynomial.Polynomial(params['GHcoefs'][ii-(ii > 1)])
            ghparams[ii]= poly(xcenter+params['Xoffset'])
        # normalization
        if ii > 0: ghparams[ii]/= numpy.sqrt(2.*numpy.pi*math.factorial(ii-1))
    # Calculate the GH part of the LSF
    out= _gausshermitebin(x,ghparams,params['binsize'])
    # Calculate the Wing part of the LSF
    out+= _wingsbin(x,wingparams,params['binsize'],params['Wproftype'])
    return out

def _gausshermitebin(x,params,binsize):
    """Evaluate the integrated Gauss-Hermite function"""
    ncenter= params.shape[1]
    out= numpy.empty((ncenter,x.shape[1]))
    integ= numpy.empty((params.shape[0]-1,x.shape[1]))
    for ii in range(ncenter):
        poly= numpy.polynomial.HermiteE(params[1:,ii])
        # Convert to regular polynomial basis for easy integration
        poly= poly.convert(kind=numpy.polynomial.Polynomial)
        # Integrate and add up
        w1= (x[ii]-0.5*binsize)/params[0,ii]
        w2= (x[ii]+0.5*binsize)/params[0,ii]
        eexp1= numpy.exp(-0.5*w1**2.)
        eexp2= numpy.exp(-0.5*w2**2.)
        integ[0]= numpy.sqrt(numpy.pi/2.)\
            *(special.erf(w2/_SQRTTWO)-special.erf(w1/_SQRTTWO))
        out[ii]= poly.coef[0]*integ[0]
        if params.shape[0] > 1:
            integ[1]= -eexp2+eexp1
            out[ii]+= poly.coef[1]*integ[1]
        for jj in range(2,params.shape[0]-1):
            integ[jj]= (-w2**(jj-1)*eexp2+w1**(jj-1)*eexp1)\
                +(jj-1)*integ[jj-2]
            out[ii]+= poly.coef[jj]*integ[jj]
    return out

def _wingsbin(x,params,binsize,Wproftype):
    """Evaluate the wings of the LSF"""
    ncenter= params.shape[1]
    out= numpy.empty((ncenter,x.shape[1]))
    for ii in range(ncenter):
        if Wproftype == 1: # Gaussian
            w1=(x[ii]-0.5*binsize)/params[1,ii]
            w2=(x[ii]+0.5*binsize)/params[1,ii]
            out[ii]= params[0,ii]/2.*(special.erf(w2/_SQRTTWO)\
                                          -special.erf(w1/_SQRTTWO))
    return out

def unpack_lsf_params(lsfarr):
    """
    NAME:
       unpack_lsf_params
    PURPOSE:
       Unpack the LSF parameter array into its constituents
    INPUT:
       lsfarr - the parameter array
    OUTPUT:
       dictionary with unpacked parameters and parameter values:
          binsize: The width of a pixel in X-units
          Xoffset: An additive x-offset; used for GH parameters that vary globally
          Horder: The highest Hermite order
          Porder: Polynomial order array for global variation of each LSF parameter
          GHcoefs: Polynomial coefficients for sigma and the Horder Hermite parameters
          Wproftype: Wing profile type
          nWpar: Number of wing parameters
          WPorder: Polynomial order for the global variation of each wing parameter          
          Wcoefs: Polynomial coefficients for the wings parameters
    HISTORY:
       2015-02-15 - Written based on Nidever's code in apogeereduce - Bovy (IAS@KITP)
    """
    out= {}
    # binsize: The width of a pixel in X-units
    out['binsize']= lsfarr[0]
    # X0: An additive x-offset; used for GH parameters that vary globally
    out['Xoffset']= lsfarr[1]
    # Horder: The highest Hermite order
    out['Horder']= int(lsfarr[2])
    # Porder: Polynomial order array for global variation of each LSF parameter
    out['Porder']= lsfarr[3:out['Horder']+4]
    out['Porder']= out['Porder'].astype('int')
    nGHcoefs= numpy.sum(out['Porder']+1)
    # GHcoefs: Polynomial coefficients for sigma and the Horder Hermite parameters
    maxPorder= numpy.amax(out['Porder'])
    GHcoefs= numpy.zeros((out['Horder']+1,maxPorder+1))
    GHpar= lsfarr[out['Horder']+4:out['Horder']+4+nGHcoefs] #all coeffs
    CoeffStart= numpy.hstack((0,numpy.cumsum(out['Porder']+1)))
    for ii in range(out['Horder']+1):
        GHcoefs[ii,:out['Porder'][ii]+1]= GHpar[CoeffStart[ii]:CoeffStart[ii]+out['Porder'][ii]+1]
    out['GHcoefs']= GHcoefs
    # Wproftype: Wing profile type
    wingarr= lsfarr[3+out['Horder']+1+nGHcoefs:]
    out['Wproftype']= int(wingarr[0])
    # nWpar: Number of wing parameters
    out['nWpar']= int(wingarr[1])
    # WPorder: Polynomial order for the global variation of each wing parameter
    out['WPorder']= wingarr[2:2+out['nWpar']]
    out['WPorder']= out['WPorder'].astype('int')
    # Wcoefs: Polynomial coefficients for the wings parameters
    maxWPorder= numpy.amax(out['WPorder'])
    Wcoefs= numpy.zeros((out['nWpar'],maxWPorder+1))
    Wpar= wingarr[out['nWpar']+2:]
    WingcoeffStart= numpy.hstack((0,numpy.cumsum(out['WPorder']+1)))
    for ii in range(out['nWpar']):
        Wcoefs[ii,:out['WPorder'][ii]+1]= Wpar[WingcoeffStart[ii]:WingcoeffStart[ii]+out['WPorder'][ii]+1]
    out['Wcoefs']= Wcoefs
    return out

def scalarDecorator(func):
    """Decorator to return scalar outputs for wave2pix and pix2wave"""
    @wraps(func)
    def scalar_wrapper(*args,**kwargs):
        if numpy.array(args[0]).shape == ():
            scalarOut= True
            newargs= (numpy.array([args[0]]),)
            for ii in range(1,len(args)):
                newargs= newargs+(args[ii],)
            args= newargs
        else:
            scalarOut= False
        result= func(*args,**kwargs)
        if scalarOut:
            return result[0]
        else:
            return result
    return scalar_wrapper

@scalarDecorator
def wave2pix(wave,chip,fiber=300):
    """
    NAME:
       wave2pix
    PURPOSE:
       convert wavelength to pixel
    INPUT:
       wavelength - wavelength (\AA)
       chip - chip to use ('a', 'b', or 'c')
       fiber= (300) fiber to use the wavelength solution of
    OUTPUT:
       pixel in the chip
    HISTORY:
        2015-02-27 - Written - Bovy (IAS)
    """
    if chip == 'a':
        wave0= _WAVEPIX_A[300-fiber]
    if chip == 'b':
        wave0= _WAVEPIX_B[300-fiber]
    if chip == 'c':
        wave0= _WAVEPIX_C[300-fiber]
    pix0= numpy.arange(len(wave0))
    # Need to sort into ascending order
    sindx= numpy.argsort(wave0)
    wave0= wave0[sindx]
    pix0= pix0[sindx]
    # Start from a linear baseline
    baseline= numpy.polynomial.Polynomial.fit(wave0,pix0,1)
    ip= interpolate.InterpolatedUnivariateSpline(wave0,pix0/baseline(wave0),
                                                 k=3)
    out= baseline(wave)*ip(wave)
    # NaN for out of bounds
    out[wave > wave0[-1]]= numpy.nan
    out[wave < wave0[0]]= numpy.nan
    return out

@scalarDecorator
def pix2wave(pix,chip,fiber=300):
    """
    NAME:
       pix2wave
    PURPOSE:
       convert pixel to wavelength
    INPUT:
       pix - pixel
       chip - chip to use ('a', 'b', or 'c')
       fiber= (300) fiber to use the wavelength solution of
    OUTPUT:
       wavelength in \AA
    HISTORY:
        2015-02-27 - Written - Bovy (IAS)
    """
    if chip == 'a':
        wave0= _WAVEPIX_A[300-fiber]
    if chip == 'b':
        wave0= _WAVEPIX_B[300-fiber]
    if chip == 'c':
        wave0= _WAVEPIX_C[300-fiber]
    pix0= numpy.arange(len(wave0))
    # Need to sort into ascending order
    sindx= numpy.argsort(pix0)
    wave0= wave0[sindx]
    pix0= pix0[sindx]
    # Start from a linear baseline
    baseline= numpy.polynomial.Polynomial.fit(pix0,wave0,1)
    ip= interpolate.InterpolatedUnivariateSpline(pix0,wave0/baseline(pix0),
                                                 k=3)
    out= baseline(pix)*ip(pix)
    # NaN for out of bounds
    out[pix < 0]= numpy.nan
    out[pix > 2047]= numpy.nan
    return out
