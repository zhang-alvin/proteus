"""
Tools for n-dimensional linear algebra

Vectors are just numpy arrays, as are dense matrices. Sparse matrices
are CSR matrices. Parallel vector and matrix are built on top of those
representations using PETSc.

.. inheritance-diagram:: proteus.LinearAlgebraTools
   :parts: 1
"""
import numpy
import math
import sys
import superluWrappers
import Comm
from .superluWrappers import *
from .Profiling import logEvent
from petsc4py import PETSc as p4pyPETSc
from . import flcbdfWrappers

def petsc_view(obj, filename):
    """Saves object to disk using a PETSc binary viewer.
    """
    viewer = p4pyPETSc.Viewer().createBinary(filename, 'w')
    viewer(obj)
    viewer2 = p4pyPETSc.Viewer().createASCII(filename+".m", 'w')
    viewer2.pushFormat(1)
    viewer2(obj)
    viewer2.popFormat()

def petsc_load_matrix(filename):
    """ This function loads a PETSc matrix from a binary format.
    (Eg. what is saved using the petsc_view function).

    Parameters
    ----------
    filename : str
        This is the name of the binary with the file stored.

    Returns
    -------
    matrix : petsc4py matrix
        The matrix that is stored in the binary file.
    """
    try:
        viewer = p4pyPETSc.Viewer().createBinary(filename,'r')
        output = p4pyPETSc.Mat().load(viewer)
    except:
        print("Either you've entered an invalid file name or your object is a vector.")
    return output

def petsc_load_vector(filename):
    """ This function loads a PETSc matrix from a binary format.
    (Eg. what is saved using the petsc_view function).

    Parameters
    ----------
    filename : str
        This is the name of the binary with the file stored.

    Returns
    -------
    matrix : petsc4py vector
        The matrix that is stored in the binary file.
    """
    try:
        viewer = p4pyPETSc.Viewer().createBinary(filename,'r')
        output = p4pyPETSc.Vec().load(viewer)
    except:
        print('invalid file name')
    return output


def _pythonCSR_2_dense(rowptr,colptr,data,nr,nc,output=False):
    """ Takes python CSR datatypes and makes a dense matrix """
    dense_matrix = numpy.zeros(shape = (nr,nc), dtype='float')
    for idx in range(len(rowptr)-1):
        row_vals = data[rowptr[idx]:rowptr[idx+1]]
        for val_idx,j in enumerate(colptr[rowptr[idx]:rowptr[idx+1]]):
            dense_matrix[idx][j] = row_vals[val_idx]
    if output is not False:
        numpy.save(output,dense_matrix)
    return dense_matrix

def superlu_sparse_2_dense(sparse_matrix,output=False):
    """ Converts a sparse superluWrapper into a dense matrix.

    Parameters
    ----------
    sparse_matrix : 
    output : str
        Out file name to store the matrix.

    Returns
    -------
    dense_matrix : numpy array
        A numpy array storing the dense matrix.

    Notes
    -----
    This function should not be used for large matrices.
    """
    rowptr = sparse_matrix.getCSRrepresentation()[0]
    colptr = sparse_matrix.getCSRrepresentation()[1]
    data   = sparse_matrix.getCSRrepresentation()[2]
    nr     = sparse_matrix.shape[0]
    nc     = sparse_matrix.shape[1]
    return _pythonCSR_2_dense(rowptr,colptr,data,nr,nc,output)

def petsc4py_sparse_2_dense(sparse_matrix,output=False):
    """ Converts a PETSc4Py matrix to a dense numpyarray.

    Parameters
    ----------
    sparse_matrix : PETSc4py matrix
    output : str
        Output file name to store the matrix.

    Returns
    -------
    dense_matrix : numpy array
        A numpy array with the dense matrix.
    
    Notes
    -----
    This function is very inefficient for large matrices.
    """
    rowptr = sparse_matrix.getValuesCSR()[0]
    colptr = sparse_matrix.getValuesCSR()[1]
    data   = sparse_matrix.getValuesCSR()[2]
    nr     = sparse_matrix.getSize()[0]
    nc     = sparse_matrix.getSize()[1]
    return _pythonCSR_2_dense(rowptr,colptr,data,nr,nc,output)

def superlu_2_petsc4py(sparse_superlu):
    """ Copy a sparse superlu matrix to a sparse petsc4py matrix

    Parameters
    ----------
    sparse_superlu : :class:`proteus.superluWrappers.SparseMatrix`

    Returns
    -------
    sparse_matrix : PETSc4py matrix
    """
    comm = Comm.get()

    if comm.size() > 1:
        rowptr,colind,nzval = sparse_superlu.getCSRrepresentation()
        A_petsc4py = ParMat_petsc4py.create_ParMat_from_OperatorConstructor(sparse_superlu)
        
    else:    
        rowptr, colind, nzval = sparse_superlu.getCSRrepresentation()
        A_rowptr = rowptr.copy()
        A_colind = colind.copy()
        A_nzval  = nzval.copy()
        nr       = sparse_superlu.shape[0]
        nc       = sparse_superlu.shape[1]
        A_petsc4py = p4pyPETSc.Mat().createAIJWithArrays((nr,nc),
                                                         (A_rowptr,
                                                          A_colind,
                                                          A_nzval))

    return A_petsc4py

def csr_2_petsc_mpiaij(size,csr):
    """ Create an MPIaij petsc4py matrix from size and CSR information.

    Parameters:
    ----------
    size : tuple
        Two entires: (num_rows, num_cols)
    csr : tuple
        (row_idx, col_idx, vals)

    Returns:
    --------
    matrix : PETSc4py MPIaij matrix
    """
    mat = p4pyPETSc.Mat().create()
    mat.setSizes(size = size)
    mat.setType('mpiaij')
    mat.setUp()
    mat.assemblyBegin()
    mat.setValuesCSR(csr[0],csr[1],csr[2])
    mat.assemblyEnd()
    return mat

class ParVec:
    """
    A parallel vector built on top of daetk's wrappers for petsc
    """
    def __init__(self,
                 array,
                 blockSize,
                 n,
                 N,
                 nghosts=None,
                 subdomain2global=None,
                 blockVecType="simple"):#"block"
        import flcbdfWrappers
        self.dim_proc=n*blockSize
        if nghosts is None:
            if blockVecType=="simple":
                self.cparVec=flcbdfWrappers.ParVec(blockSize,n,N,-1,None,array,0)
            else:
                self.cparVec=flcbdfWrappers.ParVec(blockSize,n,N,-1,None,array,1)
        else:
            assert nghosts >= 0, "The number of ghostnodes must be non-negative"
            assert subdomain2global.shape[0] == (n+nghosts), ("The subdomain2global map is the wrong length n=%i,nghosts=%i,shape=%i \n" % (n,n+nghosts,subdomain2global.shape[0]))
            assert len(array.flat) == (n+nghosts)*blockSize, ("%i  != (%i+%i)*%i \n"%(len(array.flat),  n,nghosts,blockSize))
            if blockVecType=="simple":
                self.cparVec=flcbdfWrappers.ParVec(blockSize,n,N,nghosts,subdomain2global,array,0)
            else:
                self.cparVec=flcbdfWrappers.ParVec(blockSize,n,N,nghosts,subdomain2global,array,1)
        self.nghosts = nghosts
    def scatter_forward_insert(self):
       self.cparVec.scatter_forward_insert()
    def scatter_reverse_add(self):
       self.cparVec.scatter_reverse_add()

class ParVec_petsc4py(p4pyPETSc.Vec):
    """
    Parallel vector using petsc4py's wrappers for PETSc
    
    ARB QUESTION - I think this has been implemented at this point?!
    WIP -- This function builds the local to global mapping for the PETSc parallel vectors.  At this
    point it only works when the variables can be interwoven (eg. stablized elements where velocity and
    pressure come from the same space).  We would like to extend this functionality to include finite
    element spaces that cannot be interwoven such as Taylor Hood.

    Parameters
    ----------
    array : numpy_array
            A numpy array with size equal to the number of locally
            owned unknowns plus the number of local ghost cells.
    bs : int
         Block size.
    n : int
        The number of locally owned unknowns
    N : int
        The number of unknowns in the global system
    nghosts : int
              The number of ghost nodes for the process.
    subdomain2global : numpy array
                       Map from the process unknowns to the global
                       uknowns.
    blockVecType : str
    ghosts : numpy array
             A numpy array with the local process uknowns that are
             ghost nodes.
    proteus2petsc_subdomain : numpy array
             A numpy array that serves as a map from the proteus
             uknown ordering to the petsc uknown ordering
    petsc2proteus_subdomain : numpy array
            A numpy array that serves as a map from the petsc uknown
            ordering to the proteus unknown ordering
    """
    def __init__(self,array=None,bs=None,n=None,N=None,nghosts=None,subdomain2global=None,blockVecType="simple",ghosts=None,
                                                 proteus2petsc_subdomain=None,
                                                 petsc2proteus_subdomain=None):
        p4pyPETSc.Vec.__init__(self)
        if array is None:
            return#when duplicating for petsc usage
        self.proteus2petsc_subdomain=proteus2petsc_subdomain
        self.petsc2proteus_subdomain=petsc2proteus_subdomain
        blockSize = max(1,bs)
        self.dim_proc = n*blockSize
        self.nghosts = nghosts
        self.blockVecType = blockVecType
        assert self.blockVecType == "simple", "petsc4py wrappers require self.blockVecType=simple"
        self.proteus_array = array
        if nghosts is None:
            if blockVecType == "simple":
                self.createWithArray(array,size=(blockSize*n,blockSize*N),bsize=1)
            else:
                self.createWithArray(array,size=(blockSize*n,blockSize*N),bsize=blockSize)
            self.subdomain2global=subdomain2global
            self.petsc_l2g = None
            self.setUp()
        else:
            assert nghosts >= 0, "The number of ghostnodes must be non-negative"
            assert subdomain2global.shape[0] == (n+nghosts), ("The subdomain2global map is the wrong length n=%i,nghosts=%i,shape=%i \n" % (n,n+nghosts,subdomain2global.shape[0]))
            assert len(array.flat) == (n+nghosts)*blockSize, "%i  != (%i+%i)*%i \n" % (len(array.flat),  n,nghosts,blockSize)
            if blockVecType == "simple":
                if ghosts is None:
                    ghosts = numpy.zeros((blockSize*nghosts),'i')
                    for j in range(blockSize):
                        ghosts[j::blockSize]=subdomain2global[n:]*blockSize+j
                self.createGhostWithArray(ghosts,array,size=(blockSize*n,blockSize*N),bsize=1)
                if blockSize > 1: #have to build in block dofs
                    subdomain2globalTotal = numpy.zeros((blockSize*subdomain2global.shape[0],),'i')
                    for j in range(blockSize):
                        subdomain2globalTotal[j::blockSize]=subdomain2global*blockSize+j
                    self.subdomain2global=subdomain2globalTotal
                else:
                    self.subdomain2global=subdomain2global
            else:
                #TODO need to debug
                ghosts = subdomain2global[n:]
                self.createGhostWithArray(ghosts,array,size=(blockSize*n,blockSize*N),bsize=blockSize)
                self.subdomain2global = subdomain2global
            self.setUp()
            #self.petsc_l2g = p4pyPETSc.LGMap()
            #self.petsc_l2g.create(self.subdomain2global)
            #self.setLGMap(self.petsc_l2g)
        self.setFromOptions()
    def scatter_forward_insert(self):
        if self.proteus2petsc_subdomain is not None:
            self.proteus_array[:] = self.proteus_array[self.petsc2proteus_subdomain]
        self.ghostUpdateBegin(p4pyPETSc.InsertMode.INSERT,p4pyPETSc.ScatterMode.FORWARD)
        self.ghostUpdateEnd(p4pyPETSc.InsertMode.INSERT,p4pyPETSc.ScatterMode.FORWARD)
        if self.proteus2petsc_subdomain is not None:
            self.proteus_array[:] = self.proteus_array[self.proteus2petsc_subdomain]
    def scatter_reverse_add(self):
        if self.proteus2petsc_subdomain is not None:
            self.proteus_array[:] = self.proteus_array[self.petsc2proteus_subdomain]
        self.ghostUpdateBegin(p4pyPETSc.InsertMode.ADD_VALUES,p4pyPETSc.ScatterMode.REVERSE)
        self.ghostUpdateEnd(p4pyPETSc.InsertMode.ADD_VALUES,p4pyPETSc.ScatterMode.REVERSE)
        if self.proteus2petsc_subdomain is not None:
            self.proteus_array[:] = self.proteus_array[self.proteus2petsc_subdomain]

    def save(self, filename):
        """Saves to disk using a PETSc binary viewer. """
        petsc_view(self, filename)

class ParInfo_petsc4py:
    """
    ARB - this class is experimental.  My idea is to store the
    information need to constructor parallel vectors and matrices
    here as static class values.  Then ParVec and ParMat can
    use these values to create parallel objects later.
    """
    par_bs = None
    par_n = None
    par_n_lst = None
    par_N = None
    par_nghost = None
    par_nghost_lst = None
    petsc_subdomain2global_petsc = None
    subdomain2global = None
    proteus2petsc_subdomain = None
    petsc2proteus_subdomain = None
    dim = None

    @classmethod
    def print_info(cls):
        import Comm
        comm = Comm.get()
        print 'comm.rank() = ' + `comm.rank()` + ' par_bs = ' + `cls.par_bs`
        print 'comm.rank() = ' + `comm.rank()` + ' par_n = ' + `cls.par_n`
        print 'comm.rank() = ' + `comm.rank()` + ' par_n_lst = ' + `cls.par_n_lst`
        print 'comm.rank() = ' + `comm.rank()` + ' par_N = ' + `cls.par_N`
        print 'comm.rank() = ' + `comm.rank()` + ' par_nghost = ' + `cls.par_nghost`
        print 'comm.rank() = ' + `comm.rank()` + ' par_nghost_lst = ' + `cls.par_nghost_lst`
        print 'comm.rank() = ' + `comm.rank()` + ' petsc_subdomain2global_petsc = ' + `cls.petsc_subdomain2global_petsc`
        print 'comm.rank() = ' + `comm.rank()` + ' subdomain2global = ' + `cls.subdomain2global`
        print 'comm.rank() = ' + `comm.rank()` + ' proteus2petsc_subdomain = ' + `cls.proteus2petsc_subdomain`
        print 'comm.rank() = ' + `comm.rank()` + ' petsc2proteus_subomdain = ' + `cls.petsc2proteus_subdomain`
        print 'comm.rank() = ' + `comm.rank()` + ' dim = ' + `cls.dim`

class ParMat_petsc4py(p4pyPETSc.Mat):
    """Parallel matrix based on petsc4py's wrappers for PETSc. 
    ghosted_csr_mat : :class:`proteus.superluWrappers.SparseMatrix`
        Primary CSR information for the ParMat.
    par_bs : int
        The block size.
    par_n : int
        The number of locally owned unknowns.
    par_N : int
        The number of global unknowns.
    par_nghost : int
        The number of locally owned ghost unknowns.
    subdomain2global : :class:`numpy.ndarray`
        A map from the local unknown to the global unknown.
    blockVecType : str
    pde : :class:`proteus.Transport.OneLevelTransport`
        The Transport class defining the problem.
    par_nc : int
    par_Nc : int
    proteus_jacobian : :class:`proteus.superluWrappers.SparseMatrix`
        Jacobian generated by Transport class's initializeJacobian.
    nzval_proteus2petsc : :class:`numpy.ndarray`
        ?
    """
    def __init__(self,
                 ghosted_csr_mat=None,
                 par_bs=None,
                 par_n=None,
                 par_N=None,
                 par_nghost=None,
                 subdomain2global=None,
                 blockVecType="simple",
                 pde=None,
                 par_nc=None,
                 par_Nc=None,
                 proteus_jacobian=None,
                 nzval_proteus2petsc=None):
        p4pyPETSc.Mat.__init__(self)
        if ghosted_csr_mat is None:
            return#when duplicating for petsc usage
        self.pde = pde
        if par_nc is None:
            par_nc = par_n
        if par_Nc is None:
            par_Nc = par_N
        self.proteus_jacobian=proteus_jacobian
        self.nzval_proteus2petsc = nzval_proteus2petsc
        self.ghosted_csr_mat=ghosted_csr_mat
        self.blockVecType = blockVecType
        assert self.blockVecType == "simple", "petsc4py wrappers require self.blockVecType=simple"
        self.create(p4pyPETSc.COMM_WORLD)
        self.blockSize = max(1,par_bs)
        if self.blockSize > 1 and blockVecType != "simple":
            ## \todo fix block aij in ParMat_petsc4py
            self.setType('mpibaij')
            self.setSizes([[self.blockSize*par_n,self.blockSize*par_N],[self.blockSize*par_nc,self.blockSize*par_Nc]],bsize=self.blockSize)
            self.setBlockSize(self.blockSize)
            self.subdomain2global = subdomain2global #no need to include extra block dofs?
        else:
            self.setType('mpiaij')
            self.setSizes([[par_n*self.blockSize,par_N*self.blockSize],[par_nc*self.blockSize,par_Nc*self.blockSize]],bsize=1)
            if self.blockSize > 1: #have to build in block dofs
                subdomain2globalTotal = numpy.zeros((self.blockSize*subdomain2global.shape[0],),'i')
                for j in range(self.blockSize):
                    subdomain2globalTotal[j::self.blockSize]=subdomain2global*self.blockSize+j
                self.subdomain2global=subdomain2globalTotal
            else:
                self.subdomain2global=subdomain2global
        from proteus import Comm
        comm = Comm.get()
        logEvent("ParMat_petsc4py comm.rank= %s blockSize = %s par_n= %s par_N=%s par_nghost=%s par_jacobian.getSizes()= %s "
                 % (comm.rank(),self.blockSize,par_n,par_N,par_nghost,self.getSizes()))
        self.csr_rep = ghosted_csr_mat.getCSRrepresentation()
        if self.proteus_jacobian is not None:
            self.proteus_csr_rep = self.proteus_jacobian.getCSRrepresentation()
        if self.blockSize > 1:
            blockOwned = self.blockSize*par_n
            self.csr_rep_local = ghosted_csr_mat.getSubMatCSRrepresentation(0,blockOwned)
        else:
            self.csr_rep_local = ghosted_csr_mat.getSubMatCSRrepresentation(0,par_n)
        self.petsc_l2g = p4pyPETSc.LGMap()
        self.petsc_l2g.create(self.subdomain2global)
        self.setUp()
        self.setLGMap(self.petsc_l2g)
        #
        self.colind_global = self.petsc_l2g.apply(self.csr_rep_local[1]) #prealloc needs global indices
        self.setPreallocationCSR([self.csr_rep_local[0],self.colind_global,self.csr_rep_local[2]])
        self.setFromOptions()

    def save(self, filename):
        """Saves to disk using a PETSc binary viewer.
        """
        petsc_view(self, filename)

    @classmethod
    def create_ParMat_from_OperatorConstructor(cls,
                                               operator):
        """ Build a ParMat consistent with the problem from an Operator 
        constructor matrix.

        Arguments
        ---------
        operator : :class:`proteus.superluWrappers.SparseMatrix`
            Matrix to be turned into a parallel petsc matrix.
        """
        comm = Comm.get()
        
        par_bs = ParInfo_petsc4py.par_bs
        par_n = ParInfo_petsc4py.par_n
        par_N = ParInfo_petsc4py.par_N
        par_nghost = ParInfo_petsc4py.par_nghost
        petsc_subdomain2global_petsc = ParInfo_petsc4py.petsc_subdomain2global_petsc
        subdomain2global = ParInfo_petsc4py.subdomain2global
        petsc2proteus_subdomain = ParInfo_petsc4py.petsc2proteus_subdomain
        proteus2petsc_subdomain = ParInfo_petsc4py.proteus2petsc_subdomain
        dim = ParInfo_petsc4py.dim
        # ARB - this is largely copied from Transport.py,
        # a refactor should be done to elimate this duplication
        rowptr, colind, nzval = operator.getCSRrepresentation()
        # if comm.rank()==1:
        #     print 'subdomain2global = ' + `subdomain2global`
        #     print 'rowptr = ' + `rowptr`
        #     print 'comm.rank() = ' + `nzval[95:131]`
        rowptr_petsc = rowptr.copy()
        colind_petsc = colind.copy()
        nzval_petsc = nzval.copy()
        nzval_proteus2petsc = colind.copy()
        nzval_petsc2proteus = colind.copy()
        rowptr_petsc[0] = 0

        comm.beginSequential()
        for i in range(par_n+par_nghost):
            start_proteus = rowptr[petsc2proteus_subdomain[i]]
            end_proteus = rowptr[petsc2proteus_subdomain[i]+1]
            nzrow = end_proteus - start_proteus
            rowptr_petsc[i+1] = rowptr_petsc[i] + nzrow
            start_petsc = rowptr_petsc[i]
            end_petsc = rowptr_petsc[i+1]
            petsc_cols_i = proteus2petsc_subdomain[colind[start_proteus:end_proteus]]
            j_sorted = petsc_cols_i.argsort()
            colind_petsc[start_petsc:end_petsc] = petsc_cols_i[j_sorted]
            nzval_petsc[start_petsc:end_petsc] = nzval[start_proteus:end_proteus][j_sorted]
            for j_petsc, j_proteus in zip(numpy.arange(start_petsc,end_petsc),
                                          numpy.arange(start_proteus,end_proteus)[j_sorted]):
                nzval_petsc2proteus[j_petsc] = j_proteus
                nzval_proteus2petsc[j_proteus] = j_petsc
        comm.endSequential()

        proteus_a = {}
        petsc_a = {}

        for i in range(dim):
            for j,k in zip(colind[rowptr[i]:rowptr[i+1]],range(rowptr[i],rowptr[i+1])):
                proteus_a[i,j] = nzval[k]
                petsc_a[proteus2petsc_subdomain[i],proteus2petsc_subdomain[j]] = nzval[k]
        for i in range(dim):
            for j,k in zip(colind_petsc[rowptr_petsc[i]:rowptr_petsc[i+1]],range(rowptr_petsc[i],rowptr_petsc[i+1])):
                nzval_petsc[k] = petsc_a[i,j]

        #additional stuff needed for petsc par mat

        petsc_jacobian = SparseMat(dim,dim,nzval_petsc.shape[0], nzval_petsc, colind_petsc, rowptr_petsc)
        return cls(petsc_jacobian,
                   par_bs,
                   par_n,
                   par_N,
                   par_nghost,
                   petsc_subdomain2global_petsc,
                   proteus_jacobian = operator,
                   nzval_proteus2petsc=nzval_proteus2petsc)

        
def Vec(n):
    """
    Build a vector of length n (using numpy)

    For example::
    
      >>> Vec(3)
      array([ 0.,  0.,  0.])

    """
    return numpy.zeros((n,),'d')


def Mat(m,n):
    """
    Build an m x n matrix (using numpy)

    For example::

      >>> Mat(2,3)
      array([[ 0.,  0.,  0.],
            [ 0.,  0.,  0.]])

    """
    return numpy.zeros((m,n),'d')


def SparseMatFromDict(nr,nc,aDict):
    """
    Build a nr x nc sparse matrix from a dictionary representation
    """
    import superluWrappers
    indeces = aDict.keys()
    indeces.sort()
    nnz     = len(indeces)
    nzval   = numpy.zeros((nnz,),'d')
    rowptr  = numpy.zeros((nr+1,),'i')
    colind  = numpy.zeros((nnz,),'i')
    i=0
    k=0
    rowptr[i]=0
    for ij in indeces:
        nzval[k] = aDict[ij]
        colind[k] = ij[1]
        if ij[0] > i:
            i += 1
            rowptr[i]=k
        k+=1
    rowptr[i+1] = k
    return (SparseMat(nr,nc,nnz,nzval,colind,rowptr),nzval)


def SparseMat(nr,nc,nnz,nzval,colind,rowptr):
    """ Build a nr x nc sparse matrix from the CSR data structures

    Parameters
    ----------
    nr : int
        The number of rows.
    nc : int
        The number of columns.
    nnz : int
        The number of non-zero matrix entries.
    nzval : numpy array
        Array with non-zero matrix entries.
    colind : numpy array of 32bit integers
        CSR column array.
    rowptr : numpy array of 32bit integers
        CSR row pointer.

    Returns
    -------
    sparse_matrix : :class:`proteus.superluWrappers.SparseMatrix`
        superlu sparse matrix in CSR format.

    Note
    ----
    For the superluWrapper, both the colind and rowptr should use
    32-bit integer data types.
    """
    if (colind.dtype != 'int32' or rowptr.dtype != 'int32'):
        logEvent('ERROR - colind and rowptr must be "int32" numpy arrays for ' \
                 'superluWrappers')
        sys.exit(1)
    return superluWrappers.SparseMatrix(nr,nc,nnz,nzval,colind,rowptr)

class OperatorShell:
    """ A base class for operator shells """
    def __init__(self):
        pass
    def create(self,A):
        pass

class ProductOperatorShell(OperatorShell):
    """ A base class for shell operators that apply multiplcation 
    
    Operators derived from this class should have working multiplication
    functions.
    """
    def __init__(self):
        pass
    def mult(self, A, x, y):
        raise NotImplementedError('You need to define a multiply' \
                                  'function for your shell')

class InvOperatorShell(OperatorShell):
    """ A base class for inverse operator shells 
    
    Operators derived from this class should have working apply
    functions.
    """
    def __init__(self):
        pass
    def apply(self, A, x, y):
        raise NotImplementedError('You need to define an apply' \
                                  'function for your shell')

    def _create_tmp_vec(self,size):
        """ Creates an empty vector of given size. 
        
        Arguments
        ---------
        size : int
            Size of the temporary vector.

        Returns
        -------
        vec : PETSc vector
        """
        tmp = p4pyPETSc.Vec().create()
        tmp.setType('mpi')
        tmp.setSizes(size)
        return tmp

    def _create_constant_nullspace(self):
        """Initialize a constant null space. """
        self.const_null_space = p4pyPETSc.NullSpace().create(comm=p4pyPETSc.COMM_WORLD,
                                                             vectors = (),
                                                             constant = True)
    
    def _converged_trueRes(self,ksp,its,rnorm):
        """ Function handle to feed to ksp's setConvergenceTest  """
        ksp.buildResidual(self.r_work)
        truenorm = self.r_work.norm()
#        if its >= 100:
#            import pdb ; pdb.set_trace()
        #     logEvent("!!! KSP_LACPLACE_ : %i !!!" % its)
        #     logEvent("NumericalAnalytics KSP_LSC_LaplaceResidual: %12.5e" %(truenorm) )
        #     logEvent("NumericalAnalytics KSP_LSC_LaplaceResidual(relative): %12.5e" %(truenorm / self.rnorm0) )
        #     logEvent("        KSP it %i norm(r) = %e  norm(r)/|b| = %e ; atol=%e rtol=%e " % (its,
        #                                                                                       truenorm,
        #                                                                                       (truenorm/ self.rnorm0),
        #                                                                                       ksp.atol,
        #                                                                                       ksp.rtol))
        if its == 0:
            self.rnorm0 = truenorm
            # ARB - Leaving these log events in for future debugging purposes.
            # logEvent("NumericalAnalytics KSP_LSC_LaplaceResidual: %12.5e" %(truenorm) )
            # logEvent("NumericalAnalytics KSP_LSC_LaplaceResidual(relative): %12.5e" %(truenorm / self.rnorm0) )
            # logEvent("        KSP it %i norm(r) = %e  norm(r)/|b| = %e ; atol=%e rtol=%e " % (its,
            #                                                                                   truenorm,
            #                                                                                   (truenorm/ self.rnorm0),
            #                                                                                   ksp.atol,
            #                                                                                   ksp.rtol))
            return False
        else:
            # ARB - Leaving these log events in for future debugging purposes.
            # logEvent("NumericalAnalytics KSP_LSC_LaplaceResidual: %12.5e" %(truenorm) )
            # logEvent("NumericalAnalytics KSP_LSC_LaplaceResidual(relative): %12.5e" %(truenorm / self.rnorm0) )
            # logEvent("        KSP it %i norm(r) = %e  norm(r)/|b| = %e ; atol=%e rtol=%e " % (its,
            #                                                                                   truenorm,
            #                                                                                   (truenorm/ self.rnorm0),
            #                                                                                   ksp.atol,
            #                                                                                   ksp.rtol))
            if truenorm < self.rnorm0*ksp.rtol:
                return p4pyPETSc.KSP.ConvergedReason.CONVERGED_RTOL
            if truenorm < ksp.atol:
                return p4pyPETSc.KSP.ConvergedReason.CONVERGED_ATOL
        return False


class SparseMatShell:
    """ Build a parallel matrix shell from CSR data structures.

    Parameters
    ----------
    ghosted_csr_mat: :class: `proteus.superluWrappers.SparseMatrix`
    """
    def __init__(self,ghosted_csr_mat):
        self.ghosted_csr_mat=ghosted_csr_mat
        self.par_b = None
        self.xGhosted = None
        self.yGhosted = None
    def create(self, A):
        pass
    def mult(self, A, x, y):
        assert self.par_b is not None, "The parallel RHS vector par_b must be " \
                            "initialized before using the mult function"
        logEvent("Using SparseMatShell in LinearSolver matrix multiply")
        if self.xGhosted is None:
            self.xGhosted = self.par_b.duplicate()
            self.yGhosted = self.par_b.duplicate()
        self.xGhosted.setArray(x.getArray())
        self.xGhosted.ghostUpdateBegin(p4pyPETSc.InsertMode.INSERT,p4pyPETSc.ScatterMode.FORWARD)
        self.xGhosted.ghostUpdateEnd(p4pyPETSc.InsertMode.INSERT,p4pyPETSc.ScatterMode.FORWARD)
        self.yGhosted.zeroEntries()
        with self.xGhosted.localForm() as xlf, self.yGhosted.localForm() as ylf:
            self.ghosted_csr_mat.matvec(xlf.getArray(),ylf.getArray())
        y.setArray(self.yGhosted.getArray())

class MatrixShell(ProductOperatorShell):
    """ A shell class for a matrix. """
    def __init__(self,A):
        """
        Specifies a basic matrix shell.

        Parameters
        ----------
        A : matrix
            A petsc4py matrix object
        """
        self.A = A
    def mult(self,A,x,y):
        """
        Multiply the matrix and x.

        Parameters
        ----------
        A : matrix
            Dummy place holder for PETSc compatibility
        x : vector

        Returns
        -------
        y : vector
        """
        self.A.mult(x,y)

class B_Ainv_Bt_shell(ProductOperatorShell):
    """ Shell class for the operator :math:`B A^{-1} B^{'}` """

    def __init__(self,A,B):
        """ Initialize the shell operator.
        Parameters
        ----------
        A : petsc4py matrix object
            A must be a full rank square matrix.
        B : petsc4py matrix object

        Note
        ----
        This shell is of limited use as a context matrix for use in an 
        inverse operation because of the lack of an effective 
        preconditioner.
        """
        # TODO - add an exception checking that A is a square matrix
        self.A = A
        self.B = B
        # initialize inv(A)
        self.kspA = p4pyPETSc.KSP().create()
        self.kspA.setOperators(self.A,self.A)
        self.kspA.setType('preonly')
        self.kspA.pc.setType('lu')
        self.kspA.setUp()

    def mult(self , A , x , y):
        """ This routine returns :math:`y = (B A^{-1} B^{'}) x`.
        Parameters
        ----------
        A : matrix
            Dummy matrix for PETSc interface
        x : vector
            Input vector to apply to operator
        Return
        ------
        y : vector
            Stores result of :math:`(B A^{-1} B^{'}) x`
        """
        A_sizes = self.A.getSizes()[0]
        # Initialize temporary storage containers
        temp1 = p4pyPETSc.Vec().create()
        temp2 = p4pyPETSc.Vec().create()
        temp1.setType('seq')
        temp2.setType('seq')
        temp1.setSizes(A_sizes)
        temp2.setSizes(A_sizes)
        # Apply the operator.
        self.B.multTranspose(x,temp1)
        self.kspA.solve(temp1,temp2)
        self.B.mult(temp2,y)

class MatrixInvShell(InvOperatorShell):
    """ A PETSc shell class for a inverse operator. """
    def __init__(self, A):
        """ Initializes operators and solvers for inverse operator.

        Parameters
        ----------
        A : PETSc matrix
            This is the matrix object used to construct the inverse.
        """
        self.A = A
        self.ksp = p4pyPETSc.KSP().create()
        self.ksp.setOperators(self.A,self.A)
        self.ksp.setType('preonly')
        self.ksp.pc.setType('lu')
        self.ksp.setUp()
    def apply(self,A,x,y):
        """ Apply the inverse pressure mass matrix.

        Parameters
        ----------
        A : matrix
            Dummy place holder for PETSc compatibility
        x : vector

        Returns
        -------
        y : vector
        """
        self.ksp.solve(x,y)

class TwoPhase_PCDInv_shell(InvOperatorShell):
    r""" Shell class for the two-phase PCD preconditioner.  The
    two-phase PCD_inverse shell applies the following operator.

    .. math::

        \hat{S}^{-1} = (Q^{(1 / \mu)})^{-1} + (A_{p}^{(1 / \rho)})^{-1}
        (N_{p}^{(\rho)} + \dfrac{\alpha}{\Delta t} Q^{(\rho)} ) 
        (Q^{(\rho)})^{-1}

    where :math:`Q^{(1 / \mu)}` and :math:`Q^{(\rho)}` denote the pressure 
    mass matrix scaled by the inverse dynamic viscosity and density
    respectively, :math:`(A_{p}^{(1 / \rho)})^{-1}`
    denotes the pressure Laplacian scaled by inverse density, and
    :math:`N_{p}^{(\rho)}` denotes the pressure advection operator scaled by
    the density, and :math:`\alpha` is a binary operator indicating 
    whether the problem is temporal or steady state.
    """
    def __init__(self,
                 Qp_visc,
                 Qp_dens,
                 Ap_rho,
                 Np_rho,
                 alpha = False,
                 delta_t = 0):
        """ Initialize the two-phase PCD inverse operator.
        
        Parameters
        ----------
        Qp_visc : petsc4py matrix
                  The pressure mass matrix with dynamic viscocity
                  scaling.
        Qp_dens : petsc4py matrix
                  The pressure mass matrix with density scaling.
        Ap_rho : petsc4py matrix
                 The pressure Laplacian scaled with density scaling.
        Np_rho : petsc4py matrix
                 The pressure advection operator with inverse density
                 scaling.
        alpha : binary
                True if problem is temporal, False if problem is steady
                state.
        delta_t : float
                Time step parameter.
        """
        # ARB TODO : There should be an exception to ensure each of these
        # matrices has non-zero elements along the diagonal.  I cannot
        # think of a case where this would not be an error.
        self.Qp_visc = Qp_visc
        self.Qp_dens = Qp_dens
        self.Ap_rho = Ap_rho
        self.Np_rho = Np_rho
        self.alpha = alpha
        self.delta_t = delta_t

        self._options = p4pyPETSc.Options()
        self._create_constant_nullspace()
        # TODO ARB - Need to implement the Chebyshev semi-iteration for
        # mass matrix solves.

        # Initialize mass matrix inverses.
        self.kspQp_visc = p4pyPETSc.KSP().create()
        self.kspQp_visc.setOperators(self.Qp_visc,self.Qp_visc)
        self.kspQp_visc.setOptionsPrefix('innerTPPCDsolver_Qp_visc_')
        self.kspQp_visc.setFromOptions()
        self.kspQp_visc.setUp()
        
        self.kspQp_dens = p4pyPETSc.KSP().create()
        self.kspQp_dens.setOperators(self.Qp_dens,self.Qp_dens)
        self.kspQp_dens.setOptionsPrefix('innerTPPCDsolver_Qp_dens_')
        self.kspQp_dens.setFromOptions()
        self.kspQp_dens.setUp()

        # Initialize Laplacian inverse.
        self.kspAp_rho = p4pyPETSc.KSP().create()
        self.kspAp_rho.setOperators(self.Ap_rho,self.Ap_rho)
        self.kspAp_rho.setOptionsPrefix('innerTPPCDsolver_Ap_rho_')
        self.kspAp_rho.setFromOptions()
        if self._options.hasName('innerTPPCDsolver_Ap_rho_ksp_constant_null_space'):
            self.Ap_rho.setNullSpace(self.const_null_space)
        self.kspAp_rho.setUp()

    def apply(self,A,x,y):
        """Apply the two-phase pressure-convection-diffusion preconditioner 

        Parameters
        ----------
        A : None
            Dummy variabled needed to interface with PETSc
        x : petsc4py vector
            Vector to which operator is applied

        Returns
        -------
        y : petsc4py vector
            Result of operator acting on x.
        """
        # TODO ARB - write a subroutine in InvOperatorShell
        # to create petsc4py vectors
        tmp1 = p4pyPETSc.Vec().create()
        tmp2 = p4pyPETSc.Vec().create()
        tmp3 = p4pyPETSc.Vec().create()
        tmp1.setType('mpi')
        tmp2.setType('mpi')
        tmp3.setType('mpi')
        tmp1 = x.copy()
        tmp2 = x.copy()
        tmp3 = x.copy()

        self.kspQp_visc.solve(x,y)
        self.kspQp_dens.solve(x,tmp1)

        self.Np_rho.mult(tmp1,tmp2)
        if self.alpha==True:
            tmp2.axpy(1./self.delta_t,x)

        if self._options.hasName('innerTPPCDsolver_Ap_rho_ksp_constant_null_space'):
            self.const_null_space.remove(tmp2)

        self.kspAp_rho.solve(tmp2,tmp3)
        y.axpy(1.,tmp3)
        
 
class PCDInv_shell(InvOperatorShell):
    """ Shell class for the PCD Inverse preconditioner """
    def __init__(self,Qp_matrix,Fp_matrix,Ap_matrix,bdyAdjust):
        """ Initializes the pressure-convection-diffusion inverse operator.

        Parameters
        ----------
        Qp_matrix : petsc4py matrix object
                    The pressure mass matrix.
        Fp_matrix : petsc4py matrix object
                    Convection-diffusion operator.
        Ap_matrix : petsc4py matrix object
                    The pressure Laplacian operator.
        bdyAdjust : bool
            True if improved boundary adjustment should be used.
        """
        # ARB - Chebyshev semi-iteration...
        self.Qp = Qp_matrix
        self.Fp = Fp_matrix
        self.Ap = Ap_matrix
        self.bdyAdjust = bdyAdjust
        # initialize kspAp
        self._options = p4pyPETSc.Options()

        self.kspAp = p4pyPETSc.KSP().create()
        self.kspAp.setOperators(self.Ap,self.Ap)
        self.kspAp.setOptionsPrefix('innerPCDsolver_Ap_')
        # ARB - I don't think this pc.setUp() call is necessary.
        self.kspAp.pc.setUp()

        # initialize kspQp
        self.kspQp = p4pyPETSc.KSP().create()
        self.kspQp.setOperators(self.Qp,self.Qp)
        self.kspQp.setOptionsPrefix('innerPCDsolver_Qp_')
        self.kspQp.setFromOptions()
        self.kspQp.setUp()

        self._create_constant_nullspace()
        #ARB - I need to look at this on a different problem, but I'm not sure why
        # the has_constant_null space flag does not set a constant null space on the
        # operator matrix.  It may be that the function tests for it, so I want to
        # check with a problem that actually has a constant null space.  The following
        # logic may not be necessary.
        if self._options.hasName('innerPCDsolver_Ap_ksp_constant_null_space'):
            self.Ap.setNullSpace(self.const_null_space)
        # ARB - I think the lines above are best handled from the petsc command line
        # arguments.  Remove before merge if no issues.
        # ARB does this prefix need to be here?
        # I think the answer to this is no since its gone!
        self.kspAp.setFromOptions()
        convergenceTest = 'r-true'
        if convergenceTest == 'r-true':
            self.r_work = self.Ap.getVecLeft()
            self.rnorm0 = None
            self.kspAp.setConvergenceTest(self._converged_trueRes)
        else:
            self.r_work = None        
        self.kspAp.setUp()

    def apply(self,A,x,y):
        """  
        Apply the inverse pressure-convection-diffusion operator.

        Parameters
        ----------
        A : None
            Dummy variable needed to interface with PETSc.
        x : petsc4py vector
            Vector to which operator is being applied.

        Returns
        -------
        y : petsc4py vector
            Result of operator acting on x.
        """
        x_tmp = p4pyPETSc.Vec().create(comm=p4pyPETSc.COMM_WORLD)
        temp1 = p4pyPETSc.Vec().create(comm=p4pyPETSc.COMM_WORLD)
        temp2 = p4pyPETSc.Vec().create(comm=p4pyPETSc.COMM_WORLD)
        
        x_tmp = x.copy()
        temp1 = x.copy()
        temp2 = x.copy()

        if self.bdyAdjust==True:
            self.kspQp.solve(x_tmp,temp1)
            self.Fp.mult(temp1,temp2)
            if self._options.hasName('innerPCDsolver_Ap_ksp_constant_null_space'):
                self.const_null_space.remove(temp2)
            self.kspAp.solve(temp2,y)
        else:
            if self._options.hasName('innerPCDsolver_Ap_ksp_constant_null_space'):
                self.const_null_space.remove(temp2)
            self.kspAp.solve(x_tmp,temp1)
            self.Fp.mult(temp1,temp2)
            self.kspQp.solve(temp2,y)


class LSCInv_shell(InvOperatorShell):
    """ Shell class for the LSC Inverse Preconditioner 
    
    This class creates a shell for the least-squares commutator (LSC)
    preconditioner, where 
    :math:`M_{s}= (B \hat{Q^{-1}_{v}} B^{'}) (B \hat{Q^{-1}_{v}} F 
    \hat{Q^{-1}_{v}} B^{'})^{-1} (B \hat{Q^{-1}_{v}} B^{'})` 
    is used to approximate the Schur complement.
    """
    def __init__(self, Qv, B, Bt, F):
        """Initializes the LSC inverse operator.
        
        Parameters
        ----------
        Qv : petsc4py matrix object
            The diagonal elements of the velocity mass matrix.
        B : petsc4py matrix object
            The discrete divergence operator.
        Bt : petsc4py matrix object
            The discrete gradient operator.
        F : petsc4py matrix object
            The A-block of the linear system.
        """

        # TDB - should this class take (i) a diagonal matrix
        # or (ii) the whole velocity matrix and then process the 
        # operator to be diagonal?
        # FOR NOW - assume Qv is diagonal.

        # TODO - Add an assert testing that Qv is diagonal.
        # *** - I can't find a PETSc function that does this :-(
        self.Qv = Qv
        self.B = B
        self.Bt = Bt
        self.F = F
    
        # The commented code below creates a shell for the BQvBt
        # operator.  I don't think this is the best approach but
        # in case I want to explore this in the future I've
        # left it in.
        # L_size = self.B.size[0]
        # L_sizes = (L_size,L_size)
        # self.BQinvBt = p4pyPETSc.Mat().create()
        # self.BQinvBt.setSizes(L_sizes)
        # self.BQinvBt.setType('python')
        # self.matcontext = B_Ainv_Bt_shell(self.Qv,self.B)
        # self.BQinvBt.setPythonContext(self.matcontext)
        # self.BQinvBt.setUp()
        
        # initialize (B Q_hat B')
        self.__constructBQinvBt()
        self._options = p4pyPETSc.Options()
        
        # initialize (B Q_hat B') solver
        # ARB - Adding a null space ...
        self._create_constant_nullspace()
        if self._options.hasName('innerLSCsolver_BTinvBt_ksp_constant_null_space'):
            self.BQinvBt.setNullSpace(self.const_null_space)

        self.kspBQinvBt = p4pyPETSc.KSP().create()
        self.kspBQinvBt.setOperators(self.BQinvBt,self.BQinvBt)
        self.kspBQinvBt.setOptionsPrefix('innerLSCsolver_BTinvBt_')
        self.kspBQinvBt.pc.setUp()
        self.kspBQinvBt.setFromOptions()
        self.kspBQinvBt.setUp()

        # initialize solver for Qv
        self.kspQv = p4pyPETSc.KSP().create()
        self.kspQv.setOperators(self.Qv,self.Qv)
        self.kspQv.setOptionsPrefix('innerLSCsolver_T_')
        self.kspQv.setFromOptions()
        
        convergenceTest = 'r-true'
        if convergenceTest == 'r-true':
            self.r_work = self.BQinvBt.getVecLeft()
            self.rnorm0 = None
            self.kspBQinvBt.setConvergenceTest(self._converged_trueRes)
        else:
            self.r_work = None        
        self.kspBQinvBt.setUp()

    def apply(self,A,x,y):
        """ Apply the LSC inverse operator """
        # create temporary vectors
        B_sizes = self.B.getSizes()
        x_tmp = p4pyPETSc.Vec().create()
        x_tmp = x.copy()
        if self._options.hasName('innerLSCsolver_BTinvBt_ksp_constant_null_space'):
            self.const_null_space.remove(x_tmp)
        tmp1 = self._create_tmp_vec(B_sizes[0])
        tmp2 = self._create_tmp_vec(B_sizes[1])
        tmp3 = self._create_tmp_vec(B_sizes[1])
        # apply LSC operator
        self.kspBQinvBt.solve(x_tmp,tmp1)
        self.B.multTranspose(tmp1,tmp2)
        self.kspQv.solve(tmp2,tmp3)
        self.F.mult(tmp3,tmp2)
        self.kspQv.solve(tmp2,tmp3)
        self.B.mult(tmp3,tmp1)
        if self._options.hasName('innerLSCsolver_BTinvBt_ksp_constant_null_space'):
            self.const_null_space.remove(x_tmp)
        self.kspBQinvBt.solve(tmp1,y)
        
    def __constructBQinvBt(self):
        """ Private method repsonsible for building BQinvBt """
        # Create \hat{Q}^{-1}
        self.Qv_inv = p4pyPETSc.Mat().create()
        self.Qv_inv.setSizes(self.Qv.getSizes())
        # ARB - think about correct way to initialize the matrix. (matduplicate)
        self.Qv_inv.setType('mpiaij')
        self.Qv_inv.setUp()
        self.Qv_inv.setDiagonal(1./self.Qv.getDiagonal())
        QinvBt = self.Qv_inv.matMult(self.Bt)
        self.BQinvBt = self.B.matMult(QinvBt)

    def __diagonalInverse(self, A):
        """ Construct the inverse of a diagonal matrix. 
        Parameters
        ----------
        A - petsc4py diagonal matrix
        """
        pass

def l2Norm(x):
    """
    Compute the parallel :math:`l_2` norm
    """
    return math.sqrt(flcbdfWrappers.globalSum(numpy.dot(x,x)))


def l1Norm(x):
    """
    Compute the parallel :math:`l_1` norm
    
    The :math:`l_1` norm of a vector :math:`\mathbf{x} \in
    \mathbb{R}^n` is
    
    .. math:: 
    
       \| \mathbf{x} \|_{1} = \sum_{i=0} |x_i|
    
    If Python is running in parallel, then the sum is over all
    dimensions on all processors so that the input must not contain
    "ghost" entries.
    
    This implemtation works for a distributed array with no ghost
    components (each component must be on a single processor).
    
    :param x: numpy array of length n
    :return: float
    """
    return flcbdfWrappers.globalSum(numpy.sum(numpy.abs(x)))


def lInfNorm(x):
    """
    Compute the parallel :math:`l_{\infty}` norm

    The :math:`l_{\infty}` norm of a vector :math:`\mathbf{x} \in
    \mathbb{R}^n` is

    .. math::

       \|x\|_{\infty} = \max_i |x_i|
       
    This implemtation works for a distributed array with no ghost
    components (each component must be on a single processor).
    
    :param x: numpy array of length n
    :return: float
    """
    return flcbdfWrappers.globalMax(numpy.linalg.norm(x,numpy.inf))


def wDot(x,y,h):
    """
    Compute the parallel weighted dot product of vectors x and y using
    weight vector h.
    
    The weighted dot product is defined for a weight vector
    :math:`\mathbf{h}` as

    .. math:: 

       (\mathbf{x},\mathbf{y})_h = \sum_{i} h_{i} x_{i} y_{i}
    
    All weight vector components should be positive.

    :param x,y,h: numpy arrays for vectors and weight 
    :return: the weighted dot product
    """
    return flcbdfWrappers.globalSum(numpy.sum(x*y*h))

def wl2Norm(x,h):
    """
    Compute the parallel weighted l_2 norm with weight h
    """
    return math.sqrt(flcbdfWrappers.globalSum(wDot(x,x,h)))


def wl1Norm(x,h):
    """
    Compute the parallel weighted l_1 norm with weight h
    """
    return flcbdfWrappers.globalSum(numpy.sum(numpy.abs(h*x)))


def wlInfNorm(x,h):
    """
    Compute the parallel weighted l_{\infty} norm with weight h
    """
    return flcbdfWrappers.globalMax(numpy.linalg.norm(h*x,numpy.inf))

def energyDot(x,y,A):
    """
    Compute the "energy" dot product x^t A y (not parallel)
    """
    return numpy.dot(numpy.dot(x,A),y)

def energyNorm(x,A):
    """
    Compute the "energy" norm x^t A x (not parallel)
    """
    return math.sqrt(energyDot(x,x,A))

def l2NormAvg(x):
    """
    Compute the arithmetic averaged l_2 norm (root mean squared norm)
    """
    scale = 1.0/flcbdfWrappers.globalSum(len(x.flat))
    return math.sqrt(scale*flcbdfWrappers.globalSum(numpy.dot(x,x)))


rmsNorm = l2NormAvg


def l2Norm_local(x):
    """
    Compute the l_2 norm for just local (processor) system  (not parallel)
    """
    return math.sqrt(numpy.dot(x,x))


class WeightedNorm:
    """
    Compute the weighted norm for time step control (not currently parallel)
    """
    def __init__(self,shape,atol,rtol):
        self.shape = shape
        self.dim = sum(self.shape)
        self.atol= atol
        self.rtol= rtol
        self.weight = numpy.ones(shape,'d')
        self.tmp    = numpy.ones(shape,'d')
    def setWeight(self,y):
        self.weight[:] = numpy.absolute(y)
        self.weight   *= self.rtol
        self.weight   += self.atol
    def norm(self,y,type):
        self.tmp[:] = y
        self.tmp /= self.weight
        value = numpy.linalg.norm(self.tmp.flat,type)
        return value/self.dim


if __name__ == '__main__':
    import doctest
    doctest.testmod()
    

# def test_MGV():
#     n=2**8 + 1
#     h =1.0/(n-1.0)
#     freq=10
#     u = numpy.random.uniform(0,1,(n))
#     u[0]=0.0
#     u[n-1]=0.0
#     x = numpy.arange(0,1.0+h,h)
#     AList=[]
#     N=n
#     pList=[]
#     rList=[]
#     resList=[]
#     while N >= 3:
#         resList.append(Vec(N-2))
#         A = dict()#SparseMat(N-2,N-2,3*(N-2),sym=True)
#         H = 1.0/(N-1.0)
#         #beginAssembly(A)
#         for i in range(N-2):
#             A[(i,i)] = 2.0/H**2
#             if i > 0:
#                 A[(i,i-1)] = -1.0/H**2
#             if i < N-3:
#                 A[(i,i+1)] = -1.0/H**2
#         #endAssembly(A)
#         AList.append(SparseMatFromDict(N-2,N-2,A)[0])
#         cN = (N - 1)/2 + 1
#         r = dict()#SparseMat(cN-2,N-2,3*(N-2))
#         p = dict()#SparseMat(N-2,cN-2,3*(N-2))
#         for i in range(cN-2):
#             r[(i,2*i)]   = 1.0/4.0
#             r[(i,2*i+1)] = 2.0/4.0
#             r[(i,2*i+2)] = 1.0/4.0
#             p[(2*i,i)] = 1.0/2.0
#             p[(2*i+1,i)]= 2.0/2.0
#             p[(2*i+2,i)]= 1.0/2.0
#         #r.to_csr()
#         print cN-2,N-2,r.keys()
#         if cN-2 > 0:
#             rList.append(SparseMatFromDict(cN-2,N-2,r)[0])
#         else:
#             rList.append(None)
#         #p.to_csr()
#         pList.append(SparseMatFromDict(N-2,cN-2,p)[0])
#         N = cN
#     class Jacobi:
#         def __init__(self,A):
#             self.A=A
#             self.n=A.shape[0]
#             self.M=Vec(self.n)
#             for i in range(self.n):
#                 self.M[i]=1.0/A[i,i]
#             self.res=Vec(self.n)
#             self.dx=Vec(self.n)
#         def apply(self,w,jits,b,x):
#             self.A.matvec(x,self.res)
#             self.res-=b
#             for it in range(jits):
#                 self.dx[:] = self.M*self.res
#                 self.dx*=w
#                 x -= self.dx
#                 self.A.matvec(x,self.res)
#                 self.res -= b
#     jacobiList=[]
#     for A in AList:
#         jacobiList.append(Jacobi(A))
#     jits = 3
#     w = 2.0/3.0
#     class MGV:
#         def __init__(self,smootherList,AList,pList,rList,resList):
#             self.AList = AList
#             self.pList = pList
#             self.rList = rList
#             self.resList = resList
#             self.xList=[]
#             self.vList=[]
#             self.bList=[]
#             self.gpList=[]
#             for res in resList:
#                 self.xList.append(Vec(len(res)))
#                 self.vList.append(Vec(len(res)))
#                 self.bList.append(Vec(len(res)))
#             self.smootherList = smootherList

#         def apply(self,w,nsPre,nsPost,level,b,x):
#             logEvent("Level = "+`level`)
#             if level == len(self.AList)-1:
#                 self.smootherList[level].apply(1.0,1,b,x)
#             else:
#                 #smooth
#                 self.smootherList[level].apply(w,nsPre,b,x)
#                 #restrict the defect
#                 self.rList[level].matvec(self.smootherList[level].res,self.bList[level+1])
#                 #V-cycle on the error equation
#                 self.xList[level+1][:]=0.0
#                 self.apply(w,nsPre,nsPost,level+1,self.bList[level+1],self.xList[level+1])
#                 #prolong
#                 self.pList[level].matvec(self.xList[level+1],self.vList[level])
#                 #correct
#                 x-=self.vList[level]
#                 #smooth
#                 self.smootherList[level].apply(w,nsPost,b,x)
#                 self.resList[level][:]=self.smootherList[level].res
#     mgv = MGV(jacobiList,AList,pList,rList,resList)
#     rnorm=1.0
#     mgits = 0
#     while rnorm > 1.0e-10 and mgits < 20:
#         mgits +=1
#         mgv.apply(w,jits,jits,0,f[1:n-1],u[1:n-1])
#         rnorm = l2Norm(resList[0])
