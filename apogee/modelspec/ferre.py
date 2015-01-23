###############################################################################
# ferre.py: module for interacting with Carlos Allende Prieto's FERRE code
###############################################################################
import os
import subprocess
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
        stdout= subprocess.PIPE
        stderr= subprocess.PIPE
    try:
        subprocess.check_call(['ferre'],cwd=dir,stdout=stdout,stderr=stderr)
    except subprocess.CalledProcessError:
        raise Exception("Running FERRE instance in directory %s failed ..." % dir)
    return None

def write_input_nml(dir,
                    pfile,
                    offile,
                    ndim=6,
                    nov=0,
                    synthfile=None,
                    inter=3,
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
       ndim= (6) number of dimensions/parameters
       nov= (0) number of parameters to search (0=interpolation)
       synthfile= (default ferreModelLibraryPath in apogee.tools.path) file name of the model grid's header
       inter= (3) order of the interpolation
       f_format= (1) file format (0=ascii, 1=unf)
       f_access= (1) 0: load whole library, 1: use direct access (for small numbers of interpolations)
    OUTPUT:
       (none; just writes the file)
    HISTORY:
       2015-01-22 - Written - Bovy (IAS)
    """
    if synthfile is None:
        import apogee.tools.path as appath
        synthfile= appath.ferreModelLibraryPath(header=True)
    with open(os.path.join(dir,'input.nml'),'w') as outfile:
        outfile.write('&LISTA\n')
        outfile.write('NDIM = %i\n' % ndim)
        outfile.write('NOV = %i\n' % nov)
        indvstr= 'INDV ='
        for ii in range(1,ndim+1):
            indvstr+= ' %i' % ii
        outfile.write(indvstr+'\n')
        outfile.write("SYNTHFILE(1) = '%s'\n" % synthfile)
        outfile.write("PFILE = '%s'\n" % pfile)
        outfile.write("OFFILE = '%s'\n" % offile)
        outfile.write('INTER = %i\n' % inter)
        outfile.write('F_FORMAT = %i\n' % f_format)
        outfile.write('F_ACCESS = %i\n' % f_access)
        outfile.write('/\n')
    return None
