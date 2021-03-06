#ifndef EQUIVALENT_POLYNOMIALS_H
#define EQUIVALENT_POLYNOMIALS_H
#include <cmath>
#include <cassert>
#include "equivalent_polynomials_coefficients.h"
#include "equivalent_polynomials_utils.h"

namespace equivalent_polynomials
{
  template<int nSpace, int nP, int nQ>
  class Regularized
  {
  public:
    Regularized(bool useExact=false)
    {}
    inline void calculate(const double* phi_dof, const double* phi_nodes, const double* xi_r)
    {}
    inline void set_quad(unsigned int q)
    {}
    inline double H(double eps, double phi)
    {
      double h;
      if (phi > eps)
        h=1.0;
      else if (phi < -eps)
        h=0.0;
      else if (phi==0.0)
        h=0.5;
      else
        h = 0.5*(1.0 + phi/eps + sin(M_PI*phi/eps)/M_PI);
      return h;
    }
    inline double ImH(double eps, double phi)
    {
      return 1.0-H(eps,phi);
    }
    inline double D(double eps, double phi)
    {
      double d;
      if (phi > eps)
        d=0.0;
      else if (phi < -eps)
        d=0.0;
      else
        d = 0.5*(1.0 + cos(M_PI*phi/eps))/eps;
      return d;
    }
  };
  
  template<int nSpace, int nP, int nQ>
  class Simplex
  {
  public:
    Simplex(bool useExact=true)
    {
      if (nSpace == 1)
        assert(nDOF == nP+1);
      else if (nSpace == 2)
        assert(nDOF == (nP+1)*(nP+2)/2);
      else if (nSpace == 3)
        assert(nDOF == (nP+1)*(nP+2)*(nP+3)/6);
      else
        assert(false);
      _set_Ainv<nSpace,nP>(Ainv);
    }
    
    inline void calculate(const double* phi_dof, const double* phi_nodes, const double* xi_r);

    inline void set_quad(unsigned int q)
    {
      assert(q >= 0);
      assert(q < nQ);
      _D_q = _D[q];
      if(inside_out)
        {
          _H_q   = _ImH[q];
          _ImH_q = _H[q];
        }
      else
        {
          _H_q   = _H[q];
          _ImH_q = _ImH[q];
        }
    }
    
    inline double* get_H(){return _H;};
    inline double* get_ImH(){return _ImH;};
    inline double* get_D(){return _D;};
    inline double H(double eps, double phi){return _H_q;};
    inline double ImH(double eps, double phi){return _ImH_q;};
    inline double D(double eps, double phi){return _D_q;};
    bool inside_out;
    static const unsigned int nN=nSpace+1;
    double phi_dof_corrected[nN];
  private:
    double _H_q, _ImH_q, _D_q;
    unsigned int root_node, permutation[nN];
    double phi[nN], nodes[nN*3];
    double Jac[nSpace*nSpace], inv_Jac[nSpace*nSpace];
    double level_set_normal[nSpace], X_0[nSpace], phys_nodes_cut[(nN-1)*3];
    static const unsigned int nDOF=((nSpace-1)/2)*(nSpace-2)*(nP+1)*(nP+2)*(nP+3)/6 + (nSpace-1)*(3-nSpace)*(nP+1)*(nP+2)/2 + (2-nSpace)*((3-nSpace)/2)*(nP+1);
    double Ainv[nDOF*nDOF];
    double C_H[nDOF], C_ImH[nDOF], C_D[nDOF];
    inline int _calculate_permutation(const double* phi_dof, const double* phi_nodes);
    inline void _calculate_cuts();
    inline void _calculate_C();
    inline void _correct_phi(const double* phi_dof, const double* phi_nodes);
    double _H[nQ], _ImH[nQ], _D[nQ];
  };
  
  template<int nSpace, int nP, int nQ>
  inline void Simplex<nSpace,nP,nQ>::_calculate_C()
  {
    register double b_H[nDOF], b_ImH[nDOF], b_dH[nDOF*nSpace];
    _calculate_b<nSpace,nP>(X_0, b_H, b_ImH, b_dH);

    register double Jt_dphi_dx[nSpace];
    for (unsigned int I=0; I < nSpace; I++)
      {
        Jt_dphi_dx[I] = 0.0;
        for(unsigned int J=0; J < nSpace; J++)
          Jt_dphi_dx[I] += Jac[J*nSpace + I]*level_set_normal[J];
      }
    for (unsigned int i=0; i < nDOF; i++)
      {
        C_H[i] = 0.0;
        C_ImH[i] = 0.0;
        C_D[i] = 0.0;
        for (unsigned int j=0; j < nDOF; j++)
          {
            C_H[i]   += Ainv[i*nDOF + j]*b_H[j];
            C_ImH[i] += Ainv[i*nDOF + j]*b_ImH[j];
            for (unsigned  int I=0; I < nSpace; I++)
              {
                if (fabs(Jt_dphi_dx[I]) > 0.0)
                  C_D[i]   -= Ainv[i*nDOF + j]*b_dH[j*nSpace+I]/(Jt_dphi_dx[I]);
              }
          }
      }
  }
  
  template<int nSpace, int nP, int nQ>
  inline int Simplex<nSpace,nP,nQ>::_calculate_permutation(const double* phi_dof, const double* phi_nodes)
  {
    int p_i, pcount=0, n_i, ncount=0, z_i, zcount=0;
    root_node=0;
    inside_out=false;
    for (unsigned int i=0; i < nN; i++)
      {
        if(phi_dof[i] > 0.0)
          {
            p_i = i;
            pcount  += 1;
          }
        else if(phi_dof[i] < 0.0)
          {
            n_i = i;
            ncount += 1;
          }
        else
          {
            z_i = i;
            zcount += 1;
          }
      }
    if(pcount == nN)
      {
        return 1;
      }
    else if(ncount == nN)
      {
        return -1;
      }
    else if(pcount == 1)
      {
        if (zcount == nN-1)//interface is on an element boundary, only integrate once
          return 1;
        else
          {
            if (nSpace > 1)
              {
                root_node = p_i;
                inside_out = true;
              }
            else
              {
                root_node = n_i;
              }
          }
      }
    else if(ncount == 1)
      {
        root_node = n_i;
      }
    else
      {
        assert(zcount < nN-1);
        if(pcount)
          return 1;
        else if (ncount)
          return -1;
        else
          assert(false);
      }
    for(unsigned int i=0; i < nN; i++)
      {
        permutation[i] = (root_node+i)%nN;
      }
    for(unsigned int i=0; i < nN; i++)
      {
        phi[i] = phi_dof[permutation[i]];
        for(unsigned int I=0; I < 3; I++)
          {
            nodes[i*3 + I] = phi_nodes[permutation[i]*3 + I];//nodes always 3D
          }
      }
    for(unsigned int i=0; i < nN - 1; i++)
      for(unsigned int I=0; I < nSpace; I++)
        {
          Jac[I*nSpace+i] = nodes[(1+i)*3 + I] - nodes[I];
        }
    double det_Jac = det<nSpace>(Jac);
    if(det_Jac < 0.0)
      {
        double tmp = permutation[nN-1];
        permutation[nN-1] = permutation[nN-2];
        permutation[nN-2] = tmp;
        for(unsigned int i=0; i < nN; i++)
          {
            phi[i] = phi_dof[permutation[i]];
            for(unsigned int I=0; I < 3; I++)
              {
                nodes[i*3 + I] = phi_nodes[permutation[i]*3 + I];//nodes always 3D
              }
          }
        for(unsigned int i=0; i < nN-1; i++)
          for(unsigned int I=0; I < nSpace; I++)
            Jac[I*nSpace+i] = nodes[(1+i)*3 + I] - nodes[I];
        det_Jac = det<nSpace>(Jac);
        assert(det_Jac > 0);
        if (nSpace == 1)
          inside_out = true;
      }
    inv<nSpace>(Jac, inv_Jac);
    return 0;
  }
  
  template<int nSpace, int nP, int nQ>
  inline void Simplex<nSpace,nP,nQ>::_calculate_cuts()
  {
    for (unsigned int i=0; i < nN-1;i++)
      {
        if(phi[i+1]*phi[0] < 0.0)
          {
            X_0[i] = 0.5 - 0.5*(phi[i+1] + phi[0])/(phi[i+1]-phi[0]);
            assert(X_0[i] <=1.0);
            assert(X_0[i] >=0.0);
            for (unsigned int I=0; I < 3; I++)
              {
                phys_nodes_cut[i*3 + I] = (1-X_0[i])*nodes[I] + X_0[i]*nodes[(1+i)*3 + I];
              }
          }
        else
          {
            assert(phi[i+1] == 0.0);
            X_0[i] = 1.0;
            for (unsigned int I=0; I < 3; I++)
              {
                phys_nodes_cut[i*3 + I] = nodes[(1+i)*3 + I];
              }
          }
      }
  }
  
  template<int nSpace, int nP, int nQ>
  inline void Simplex<nSpace,nP,nQ>::_correct_phi(const double* phi_dof, const double* phi_nodes)
  {
    register double cut_barycenter[3] ={0.,0.,0.};
    const double one_by_nNm1 = 1.0/(nN-1.0);
    for (unsigned int i=0; i < nN-1;i++)
      {
        for (unsigned int I=0; I < nSpace; I++)
          cut_barycenter[I] += phys_nodes_cut[i*3+I]*one_by_nNm1;
      }
    for (unsigned int i=0; i < nN;i++)
      {
        phi_dof_corrected[i]=0.0;
        for (unsigned int I=0; I < nSpace; I++)
          {
            phi_dof_corrected[i] += level_set_normal[I]*(phi_nodes[i*3+I] - cut_barycenter[I]);             
          }
        //todo: decide if we should just use a consistant normal
        if (phi_dof_corrected[i]*phi_dof[i] < 0.0)
          {
            phi_dof_corrected[i]*=-1.0;
          }
      }
  }
  
  template<int nSpace, int nP, int nQ>
  inline void Simplex<nSpace,nP,nQ>::calculate(const double* phi_dof, const double* phi_nodes, const double* xi_r)
  {
    //initialize phi_dof_corrected -- correction can only be actually computed on cut cells
    for (unsigned int i=0; i < nN;i++)
      phi_dof_corrected[i] = phi_dof[i];
    int icase = _calculate_permutation(phi_dof, phi_nodes);//permuation, Jac,inv_Jac...
    if(icase == 1)
      {
        for (unsigned int q=0; q < nQ; q++)
          {
            _H[q] = 1.0;
            _ImH[q] = 0.0;
            _D[q] = 0.0;
          }
        return;
      }
    else if(icase == -1)
      {
        for (unsigned int q=0; q < nQ; q++)
          {
            _H[q] = 0.0;
            _ImH[q] = 1.0;
            _D[q] = 0.0;
          }
        return;
      }
    _calculate_cuts();//X_0, array of interface cuts on reference simplex
    _calculate_normal<nSpace>(phys_nodes_cut, level_set_normal);//normal to interface
    _calculate_C();//coefficients of equiv poly
    _correct_phi(phi_dof, phi_nodes);
    //compute the default affine map based on phi_nodes[0]
    double Jac_0[nSpace*nSpace];
    for(unsigned int i=0; i < nN - 1; i++)
      for(unsigned int I=0; I < nSpace; I++)
        Jac_0[I*nSpace+i] = phi_nodes[(1+i)*3 + I] - phi_nodes[I];
    for(unsigned int q=0; q < nQ; q++)
      {
        //Due to the permutation, the quadrature points on the reference may be rotated
        //map reference to physical simplex, then back to permuted reference
        register double x[nSpace], xi[nSpace];
        //to physical coordinates
        for (unsigned int I=0; I < nSpace; I++)
          {
            x[I]=phi_nodes[I];
            for (unsigned int J=0; J < nSpace;J++)
              {
                x[I] += Jac_0[I*nSpace + J]*xi_r[q*3 + J];
              }
          }
        //back to reference coordinates on possibly permuted 
        for (unsigned int I=0; I < nSpace; I++)
          {
            xi[I] = 0.0;
            for (unsigned int J=0; J < nSpace; J++)
              {
                xi[I] += inv_Jac[I*nSpace + J]*(x[J] - nodes[J]);
              }
          }
        if (nSpace == 1)
          _calculate_polynomial_1D<nP>(xi,C_H,C_ImH,C_D,_H[q],_ImH[q],_D[q]);
        else if (nSpace == 2)
          _calculate_polynomial_2D<nP>(xi,C_H,C_ImH,C_D,_H[q],_ImH[q],_D[q]);
        else if (nSpace == 3)
          _calculate_polynomial_3D<nP>(xi,C_H,C_ImH,C_D,_H[q],_ImH[q],_D[q]);
      }
    set_quad(0);
  }

  template<int nSpace, int nP, int nQ>
  class GeneralizedFunctions_mix
  {
  public:
    Regularized<nSpace, nP, nQ> regularized;
    Simplex<nSpace, nP, nQ> exact;
    bool useExact;
    GeneralizedFunctions_mix(bool useExact=true):
      useExact(useExact)
    {}
    
    inline void calculate(const double* phi_dof, const double* phi_nodes, const double* xi_r)
    {
      //hack for testing
      exact.calculate(phi_dof, phi_nodes, xi_r);
      /* if(useExact) */
      /*   exact.calculate(phi_dof, phi_nodes, xi_r); */
      /* else//for inexact just copy over local phi_dof */
      /*   for (int i=0; i<exact.nN;i++) */
      /*     exact.phi_dof_corrected[i] = phi_dof[i]; */
      /* for (int i=0; i<exact.nN;i++) */
      /*   exact.phi_dof_corrected[i] = phi_dof[i]; */
    }
    
    inline void set_quad(unsigned int q)
    {
      if(useExact)
        exact.set_quad(q);
    }
    
    inline double H(double eps, double phi)
    {
      if(useExact)
        return exact.H(eps, phi);
      else
        return regularized.H(eps, phi);
    }

    inline double ImH(double eps, double phi)
    {
      if(useExact)
        return exact.ImH(eps, phi);
      else
        return regularized.ImH(eps, phi);
    }
    
    inline double D(double eps, double phi)
    {
      if(useExact)
        return exact.D(eps, phi);
      else
        return regularized.D(eps, phi);
    }
  };
}//equivalent_polynomials

#endif
