#ifndef CREATE_ANALYTIC_H
#define CREATE_ANALYTIC_H

#include <apf.h>
#include <apfMDS.h>
#include <apfMesh2.h>
#include <apfShape.h>

#include <PCU.h>
#include <gmi_analytic.h>
#include <gmi_mesh.h>

#include <cassert>
#include <stdlib.h>

#include <iostream>
#include <fstream>
#include<map>
#include <math.h>
#include <pcu_util.h>

agm_bdry add_bdry(gmi_model* m, gmi_ent* e);
agm_use add_adj(gmi_model* m, agm_bdry b, int tag);
agm_use add_adj(gmi_model* m, agm_bdry b, int dim, int tag);

#endif
