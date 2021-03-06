from __future__ import division
from past.utils import old_div
from proteus import *
from proteus.default_n import *
from proteus.mprans import SW2DCV
import sw_p

# ******************************************** #
# ********** READ FROM PHYSICS FILE ********** #
# ******************************************** #
nd = sw_p.nd
T = sw_p.T
nDTout = sw_p.nDTout
runCFL = sw_p.runCFL
he = sw_p.he
useSuperlu = sw_p.useSuperlu
domain = sw_p.domain
SSPOrder = sw_p.SSPOrder
LUMPED_MASS_MATRIX = sw_p.LUMPED_MASS_MATRIX
reflecting_BCs = sw_p.reflecting_BCs

# *************************************** #
# ********** MESH CONSTRUCTION ********** #
# *************************************** #
if domain is not None:
    triangleFlag = sw_p.triangleFlag
    nnx = sw_p.nnx
    nny = sw_p.nny
    nnz = 1
    triangleOptions = domain.MeshOptions.triangleOptions

# ************************************** #
# ********** TIME INTEGRATION ********** #
# ************************************** #
timeIntegration = SW2DCV.RKEV
timeOrder = SSPOrder
nStagesTime = SSPOrder

# ****************************************** #
# ********** TIME STEP CONTROLLER ********** #
# ****************************************** #
stepController = Min_dt_controller

# ******************************************* #
# ********** FINITE ELEMENT SAPCES ********** #
# ******************************************* #
elementQuadrature = SimplexGaussQuadrature(nd,3)
elementBoundaryQuadrature = SimplexGaussQuadrature(nd-1,3)
femSpaces = {0:C0_AffineLinearOnSimplexWithNodalBasis,
             1:C0_AffineLinearOnSimplexWithNodalBasis,
             2:C0_AffineLinearOnSimplexWithNodalBasis}

# ************************************** #
# ********** NONLINEAR SOLVER ********** #
# ************************************** #
multilevelNonlinearSolver  = Newton
fullNewtonFlag = False 
if (LUMPED_MASS_MATRIX==1):
    levelNonlinearSolver = ExplicitLumpedMassMatrixShallowWaterEquationsSolver
else:
    levelNonlinearSolver = ExplicitConsistentMassMatrixShallowWaterEquationsSolver
    
# ************************************ #
# ********** NUMERICAL FLUX ********** #
# ************************************ #
numericalFluxType = SW2DCV.NumericalFlux

# ************************************ #
# ********** LINEAR ALGEBRA ********** #
# ************************************ #
matrix = SparseMatrix
multilevelLinearSolver = LU
levelLinearSolver = LU
levelNonlinearSolverConvergenceTest = 'r'
linearSolverConvergenceTest = 'r-true'

# ******************************** #
# ********** TOLERANCES ********** #
# ******************************** #
nl_atol_res = 1.0e-5
nl_rtol_res = 0.0
l_atol_res = 1.0e-7
l_rtol_res = 0.0
tolFac = 0.0
maxLineSearches=0

# **************************** #
# ********** tnList ********** #
# **************************** #
tnList=[0.,1E-6]+[float(n)*T/float(nDTout) for n in range(1,nDTout+1)]

# **************************** #
# ********** GAUGES ********** #
# **************************** #
from proteus.Gauges import PointGauges
p = PointGauges(gauges=(( ('h'), ((5550.0,4400.0, 0),
                                  (11900.0,3250.0,0),
                                  (13000.0,2700.0,0),
                                  (4947.46,4289.71, 0), 
                                  (5717.30,4407.61, 0),
                                  (6775.14,3869.23, 0), 
                                  (7128.20,3162.00, 0), 
                                  (8585.30,3443.08, 0), 
                                  (9674.97,3085.89, 0), 
                                  (10939.15,3044.78, 0), 
                                  (11724.37,2810.41, 0), 
                                  (12723.70,2485.08, 0)) ),),
                activeTime=(0, 3000),
                sampleRate=0.1,
                fileName='gauges.csv')
auxiliaryVariables=[p]
