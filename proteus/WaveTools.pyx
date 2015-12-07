# A type of -*- python -*- file
#cython: embedsignature=True
"""Tools for working with water waves.

The primary objective of this module is to provide solutions (exact and
approximate) for the free surface deformation and subsurface velocity
components of water waves. These can be used as boundary conditions, wave
generation sources, and validation solutions for numerical wave codes.

.. inheritance-diagram:: ShockCapturing
    :parts: 2
"""
from math import pi, tanh, sqrt, exp, log, sin, cos, cosh, sinh
import numpy as np
import cmath as cmath
from Profiling import logEvent
import time as tt
import sys as sys


def loadExistingFunction(funcName, validFunctions):
    funcNames = []
    for func  in validFunctions:
            funcNames.append(func.__name__)
            if func.__name__ == funcName:
                func_ret = func
    if funcName not in funcNames:
        logEvent("WaveTools.py: Wrong function type (%s) given: Valid wavetypes are %s" %(funcName,funcNames), level=0)
        sys.exit(1)
    return func_ret
       


def setVertDir(g):
    """ Sets the unit vector for the vertical direction, opposite to the gravity vector
    param: g : gravitational acceleration vector [L/T^2]
    """
    return -g/(sqrt(g[0]**2 + g[1]**2 + g[2]**2))

def setDirVector(vector):
    """ Returns the direction of a vector in the form of a unit vector
    param: vector : Any vector [-]
    """
    return vector/(sqrt(vector[0]**2 + vector[1]**2 + vector[2]**2))

def dirCheck(v1, v2):
    """ Checks if to vectors are vertical and returns system exit if not
    param: v1 : 1st vector  [-]
    param: v2 : 2nd vector  [-]
    """
    dircheck = abs(v1[0]*v2[0]+v1[1]*v2[1]+v1[2]*v2[2])
        #print self.dircheck
    if dircheck > 1e-10:
        logEvent("Wave direction is not perpendicular to gravity vector. Check input",level=0)
        return sys.exit(1)
    else:
        return None
def reduceToIntervals(fi,df):
    """ Prepares the x- axis array of size N for numerical integration along he x- axis. 
    If fi = [a1, a2, a3,...,a_N-1 a_N] then it returns the array 
    [a1, 0.5(a1+a2), 0.5(a2+a3),...0.5(a_N-1+a_N), a_N]. Input array must have constant step
    param: fi : x- array  [-]
    param: df : dx constant step of array  [-]
    """
    fim_tmp = (0.5*(fi[1:]+fi[:-1])).tolist()
    return np.array([fim_tmp[0]-0.5*df]+fim_tmp+[fim_tmp[-1]+0.5*df])
def returnRectangles(a,x):
    """ Returns \delta y of y(x) using the rectangle method (\delta y = 0.5*(a_n-1+a_n)*(x_n-1-x_n) 
    param: a : y(x) function   [-]
    param: x : x- coordinate  [-]
    """
    return 0.5*(a[1:]+a[:-1])*(x[1:]-x[:-1])
def returnRectangles3D(a,x,y):
    """ Returns \delta y of  y(x,z) using the rectangle method 
    \delta y = 0.25*(a_(n-1,m-1)+a_(n,m-1)+a_(n-1,m)+a_(n,m))*(x_n-1-x_n) *(z_m-1-z_m)
    param: a : y(x,z) function   [-]
    param: x : x- coordinate  [-]
    param: z : z- coordinate  [-]
    """
    ai = 0.5*(a[1:,:]+a[:-1,:])
    ai = 0.5*(ai[:,1:]+ai[:,:-1])
    for ii in range(len(x)-1):
        ai[ii,:] *= (y[1:]-y[:-1]) 
    for jj in range(len(y) - 1):
        ai[:,jj] *= (x[1:]-x[:-1])    
    return ai
def normIntegral(Sint,th):
    """Given an Sint(th) function, it returns Sint_n, such as \int (Sint_n dth = 1)
    param: Sint : Sint(th) function   [-]
    param: th : th- coordinate  [-]
    """
    G0 = 1./sum(returnRectangles(Sint,th))
    return G0*Sint



def eta_mode(x,y,z,t,kDir,omega,phi,amplitude):
    """Returns a single frequency mode for free-surface elevation at point x,y,z,t
    :param kDir: wave number vector [1/L]
    :param omega: angular frequency [1/T]
    :param phi: phase [0,2*pi]
    :param amplitude: wave amplitude [L/T^2]
    """
    phase = x*kDir[0]+y*kDir[1]+z*kDir[2] - omega*t  + phi
    return amplitude*cos(phase)


def vel_mode(x,y,z,t,kDir,kAbs,omega,phi,amplitude,mwl,depth,g,vDir,comp):
    """Returns a single frequency mode for velocity at point x,y,z,t
    :param kDir: wave number vector [1/L]
    :param omega: angular frequency [1/T]
    :param phi: phase [0,2*pi]
    :param amplitude: wave amplitude [L/T^2]
    :param mwl: mean water level [L]
    :param depth: water depth [L]
    :param g: gravity vector
    :param vDir (vertical direction - opposite to the gravity vector)
    :param comp: component "x", "y" or "z"
    """

    phase = x*kDir[0]+y*kDir[1]+z*kDir[2] - omega*t  + phi
    Z =  (vDir[0]*x + vDir[1]*y+ vDir[2]*z) - mwl
    UH = 0.
    UV=0.
    ii=0.
    UH=amplitude*omega*cosh(kAbs*(Z + depth))*cos( phase )/sinh(kAbs*depth)
    UV=amplitude*omega*sinh(kAbs*(Z + depth))*sin( phase )/sinh(kAbs*depth)
    waveDir = kDir/kAbs
#waves(period = 1./self.fi[ii], waveHeight = 2.*self.ai[ii],mwl = self.mwl, depth = self.d,g = self.g,waveDir = self.waveDir,wavelength=self.wi[ii], phi0 = self.phi[ii]).u(x,y,z,t)
    Vcomp = {
        "x":UH*waveDir[0] + UV*vDir[0],
        "y":UH*waveDir[1] + UV*vDir[1],
        "z":UH*waveDir[2] + UV*vDir[2],
        }
    return Vcomp[comp]



def sigma(omega,omega0):
    """sigma function for JONSWAP spectrum
       http://www.wikiwaves.org/Ocean-Wave_Sectra
    """
    sigmaReturn = np.where(omega > omega0,0.09,0.07)
    return sigmaReturn


def JONSWAP(f,f0,Hs,gamma=3.3,TMA=False, depth = None):
    """The wave spectrum from Joint North Sea Wave Observation Project
    Jonswap equation from "Random Seas and Design of Maritime Structures" - Y. Goda - 2010 (3rd ed) eq. 2.12 - 2.15
    TMA modification from "Random Seas and Design of Maritime Structures" - Y. Goda - 2010 (3rd ed) eq. 2.19
    :param f: wave frequency [1/T] (not angular frequency)
    :param f0: direcpeak frequency [1/T] (not angular frequency)
    :param Hs: significant wave height [L]
    :param g: gravity [L/T^2]
    :param gamma: peak enhancement factor [-]
    """
    Tp = 1./f0
    bj = 0.0624*(1.094-0.01915*log(gamma))/(0.23+0.0336*gamma-0.185/(1.9+gamma))
    r = np.exp(-(Tp*f-1.)**2/(2.*sigma(f,f0)**2))
    tma = 1.
    if TMA:
        if (depth == None):
            logEvent("Wavetools:py. Provide valid depth definition definition for TMA spectrum")
            logEvent("Wavetools:py. Stopping simulation")
            exit(1)
        k = dispersion(2*pi*f,depth)
        tma = np.tanh(k*depth)*np.tanh(k*depth)/(1.+ 2.*k*depth/np.sinh(2.*k*depth))

    return tma * bj*(Hs**2)*(1./((Tp**4) *(f**5)))*np.exp(-1.25*(1./(Tp*f)**(4.)))*(gamma**r)

def PM_mod(f,f0,Hs):
    """modified Pierson-Moskovitz spectrum (or Bretschneider or ISSC)
    Reference http://www.orcina.com/SoftwareProducts/OrcaFlex/Documentation/Help/Content/html/Waves,WaveSpectra.htm
    And then to Tucker M J, 1991. Waves in Ocean Engineering. Ellis Horwood Ltd. (Chichester).
    :param f: frequency [1/T]
    :param f0: peak frequency [1/T]
    :param alpha: alpha fitting parameter [-]
    :param beta: beta fitting parameter [-]
    :param g: graivty [L/T^2]
    """
    return (5.0/16.0)*Hs**2*(f0**4/f**5)*np.exp((-5.0/4.0)*(f0/f)**4)

def cos2s(theta,f,s=10):
    """The cos2s wave directional Spread 
    see USACE - CETN-I-28 http://chl.erdc.usace.army.mil/library/publications/chetn/pdf/cetn-i-28.pdf
    :param theta: ange of wave direction, with respect to the peak direction
    :param f: wave frequency [1/T] (not angular frequency). Dummy variable in this one
    :param s: directional peak parameter. as s ->oo the distribution converges to 
    """
    fun = np.zeros((len(theta),len(f)),)
    for ii in range(len(fun[0,:])):
        fun[:,ii] = np.cos(theta/2)**(2*s)
    return fun
def mitsuyasu(theta,fi,f0,smax=10):
    """The cos2s wave directional spread with wave frequency dependency (mitsuyasu spreas) 
    Equation from "Random Seas and Design of Maritime Structures" - Y. Goda - 2010 (3rd ed) eq. 2.22 - 2.25
    :param theta: ange of wave direction, with respect to the peak direction
    :param f: wave frequency [1/T] (not angular frequency). Dummy variable in this one
    :param s: directional peak parameter. as s ->oo the distribution converges to 
    """

    s = smax * (fi/f0)**(5)
    ii = np.where(fi>f0)[0][0]
    s[ii:] = smax * (fi[ii:]/f0)**(-2.5)
    fun = np.zeros((len(theta),len(fi)),)
    for ii in range(len(fun[0,:])):
        fun[:,ii] = np.cos(theta/2)**(2.*s[ii])
    return fun





def dispersion(w,d, g = 9.81,niter = 1000):
    """Calculates wave vector k from linear dispersion relation

    :param w: cyclical frequency
    :param d: depth [L]
    :param niter: number  of solution iterations
    :param g: gravity [L/T^2
    """
#    print("Initiating dispersion")
    w_aux = np.array(w)
    Kd = w_aux*sqrt(d/g)
#    print("Initial dispersion value = %s" %str(Kd/d))
    for jj in range(niter):
       #Kdn_1 = Kd
        Kd =  w_aux* w_aux/g/np.tanh(Kd)
        #Kdn_1 /=0.01*Kd
        #Kdn_1 -= 100.
        #Kdn_1 = abs(Kdn_1)
        #try: Kdn_1 = mean(Kdn_1)
        #except: continue
    #print "Solution convergence for dispersion relation %s percent" % Kdn_1
#    print("Final k value = %s" %str(Kd/d))
#    print("Wavelength= %s" %str(2.*pi*d/Kd))
    if type(Kd) is float:
        return Kd[0]/d
    else:
        return(Kd/d)


def tophat(l,cutoff):
    """ returns a top hat filter 
    :param l: array length
    :param l: cut off fraction at either side of the array zero values will be imposed at the first and last cutoff*l array elements

    """
    a = np.zeros(l,)
    cut = int(cutoff*l)
    a[cut:-cut] = 1.
    return a

def costap(l,cutoff=0.1):
    """ Cosine taper filter Goda (2010), Random Seas and Design of Maritime Structures equation 11.40   
    :param l: array length
    :param l: cut off fraction at either side of the array zero values will be imposed at the first and last cutoff*l array elements"""
    npoints = int(cutoff*l)
    wind = np.ones(l)
    for k in range(l): # (k,np) = (n,N) normally used
        if k < npoints:
            wind[k] = 0.5*(1.-cos(pi*float(k)/float(npoints)))
        if k > l - npoints -1:
            wind[k] = 0.5*(1.-cos(pi*float(l-k-1)/float(npoints)))
    return wind

def decompose_tseries(time,eta):
    """ This function does a spectral decomposition of a time series with constant sampling.
     It returns a list with results with four entries:
         0 -> numpy array with frequency components ww
         1 -> numpy array with amplitude of each component aa
         2 -> numpy array with phase of each component pp
         3 -> float of the 0th fourier mode (wave setup) 
         :param : time array [T]
         :param : signal array
         """
    nfft = len(time) 
    NN = int(np.ceil((nfft+1)/2)-1)
    results = []
    fft_x = np.fft.fft(eta,nfft)                                   #%complex spectrum
    setup = np.real(fft_x[0])/nfft
    fft_x = fft_x[1:NN+1]                              #%retaining only first half of the spectrum
    aa = abs(fft_x)/nfft                                 #%amplitudes (only the ones related to positive frequencies)
    if nfft%2:                                       #%odd nfft- excludes Nyquist point
      aa[0:NN] = 2.*aa[0:NN]
    else:                                               
      aa[0:NN -1] = 2.* aa[0:NN -1]
    ww = np.linspace(1,NN,NN)*2*pi/(time[2]-time[1])/nfft     
    

    pp = np.zeros(len(aa),complex)
    for k in range(len(aa)):
        pp[k]=cmath.phase(fft_x[k])                       #% Calculating phases phases
    pp = np.real(pp)                                         # Append results to list
    results.append(ww)
    results.append(aa)
    results.append(pp)
    results.append(setup)
    return results





class MonochromaticWaves:
    """Generate a monochromatic wave train in the linear regime
    """
    def __init__(self,
                 period,
                 waveHeight,
                 mwl,
                 depth,
                 g,
                 waveDir,
                 wavelength=None,
                 waveType="Linear",
                 Ycoeff = None, 
                 Bcoeff =None, meanVelocity = np.array([0.,0,0.]),
                 phi0 = 0.):

        self.knownWaveTypes = ["Linear","Fenton"]
        self.waveType = waveType
        if self.waveType not in self.knownWaveTypes:
            logEvent("Wrong wavetype given: Valid wavetypes are %s" %(self.knownWaveTypes), level=0)
            sys.exit(1)
        self.g = np.array(g)
        self.waveDir =  setDirVector(np.array(waveDir))
        self.vDir = setVertDir(g)
        self.gAbs = sqrt(self.g[0]*self.g[0]+self.g[1]*self.g[1]+self.g[2]*self.g[2])

#Checking if g and waveDir are perpendicular
        dirCheck(self.waveDir,self.vDir)
        self.phi0=phi0
        self.period = period
        self.waveHeight = waveHeight
        self.mwl = mwl
        self.depth = depth
        self.omega = 2.0*pi/period

#Calculating / checking wavelength data
        if  self.waveType is "Linear":
            self.k = dispersion(w=self.omega,d=self.depth,g=self.gAbs)
            self.wavelength = 2.0*pi/self.k
        else:
            try:
                self.k = 2.0*pi/wavelength
                self.wavelength=wavelength
            except:
                logEvent("WaveTools.py: Wavelenght is not defined for nonlinear waves. Enter wavelength in class arguments",level=0)
                sys.exit(1)
        self.kDir = self.k * self.waveDir
        self.amplitude = 0.5*self.waveHeight
        self.meanVelocity = {
        "x": meanVelocity[0],
        "y": meanVelocity[1],
        "z":  meanVelocity[2]
        }
#Checking that meanvelocity is a vector

        if(len(meanVelocity) != 3):
            logEvent("WaveTools.py: meanVelocity should be a vector with 3 components. ",level=0)
            sys.exit(1)

        self.Ycoeff = Ycoeff
        self.Bcoeff = Bcoeff

# Checking for
        if (Ycoeff is None) or (Bcoeff is None):
            if self.waveType is not "Linear":
                logEvent("WaveTools.py: Need to define Ycoeff and Bcoeff (free-surface and velocity) for nonlinear waves",level=0)
                sys.exit(1)
    def eta(self,x,y,z,t):
        if self.waveType is "Linear":
            return eta_mode(x,y,z,t,self.kDir,self.omega,self.phi0,self.amplitude)
        elif self.waveType is "Fenton":
            HH = 0.
            ii =0.
            for Y in self.Ycoeff:
                ii+=1
                HH+=eta_mode(x,y,z,t,ii*self.kDir,ii*self.omega,self.phi0,Y)
            return HH/self.k

    def u(self,x,y,z,t,comp):
        if self.waveType is "Linear":
            return vel_mode(x,y,z,t,self.kDir,self.k,self.omega,self.phi0,self.amplitude,self.mwl,self.depth,self.g,self.vDir,comp)
        elif self.waveType is "Fenton":
            Ufenton = self.meanVelocity[comp]
            ii = 0
            for B in self.Bcoeff:
                ii+=1
                wmode = ii*self.omega
                kmode = ii*self.k
                kdir = self.waveDir*kmode
                amp = tanh(kmode*self.depth)*sqrt(self.gAbs/self.k)*B/self.omega
                Ufenton+= vel_mode(x,y,z,t,kdir,kmode,wmode,self.phi0,amp,self.mwl,self.depth,self.g,self.vDir,comp)
            return Ufenton # + self.meanVelocity[comp]


class RandomWaves:
    """Generate approximate random wave solutions
    :param Tp: frequency [1/T]
    :param Hs: significant wave height [L]
    :param mwl: mean water level [L]
    :param  depth: depth [L]
    :param waveDir:wave Direction vector [-]
    :param g: Gravitational acceleration vector [L/T^2]
    :param N: number of frequency bins [-]
    :param bandFactor: width factor for band  around fp [-]
    :param spectName: Name of spectral function. Use a random word and run the code to obtain the vaild spectra names
    :param spectral_params: Additional arguments for spectral function, specific to each spectral function. If set to none, only Hs and Tp are given as parameters
    :param phi: Array of component phases - if set to none, random phases are assigned
"""

    def __init__(self,
                 Tp,
                 Hs,
                 mwl,#m significant wave height
                 depth ,           #m depth
                 waveDir,
                 g,      #peak  frequency
                 N,
                 bandFactor,         #accelerationof gravity
                 spectName ,# random words will result in error and return the available spectra 
                 spectral_params =  None, #JONPARAMS = {"gamma": 3.3, "TMA":True,"depth": depth} 
                 phi=None
                 ):
        validSpectra = [JONSWAP,PM_mod]
        spec_fun =loadExistingFunction(spectName, validSpectra)                 
        self.g = np.array(g)
        self.waveDir =  setDirVector(np.array(waveDir))
        self.vDir = setVertDir(g)
        dirCheck(self.waveDir,self.vDir)
        self.gAbs = sqrt(self.g[0]*self.g[0]+self.g[1]*self.g[1]+self.g[2]*self.g[2])
        self.Hs = Hs
        self.depth = depth
        self.Tp = Tp
        self.fp = 1./Tp
        self.bandFactor = bandFactor
        self.N = N
        self.mwl = mwl
        self.fmax = self.bandFactor*self.fp
        self.fmin = self.fp/self.bandFactor
        self.df = (self.fmax-self.fmin)/float(self.N-1)
        self.fi = np.linspace(self.fmin,self.fmax,self.N)
        self.omega = 2.*pi*self.fi
        self.ki = dispersion(self.omega,self.depth,g=self.gAbs)
        if phi == None:
            self.phi = 2.0*pi*np.random.random(self.fi.shape[0])
            logEvent('WaveTools.py: No phase array is given. Assigning random phases. Outputing the phasing of the random waves')
        else:
            try: 
                self.phi = np.array(phi)
                if self.phi.shape[0] != self.fi.shape[0]:
                    logEvent('WaveTools.py: Phase array must have N elements')
                    sys.exit(1)
                    
            except:
                logEvent('WaveTools.py: phi argument must be an array with N elements')
                exit(1)

        #ai = np.sqrt((Si_J[1:]+Si_J[:-1])*(fi[1:]-fi[:-1]))
        self.fim = reduceToIntervals(self.fi,self.df)
        if (spectral_params == None):
            self.Si_Jm = spec_fun(self.fim,self.fp,self.Hs)
        else:
            try:
                self.Si_Jm = spec_fun(self.fim,self.fp,self.Hs,**spectral_params)
            except:
                logEvent('WaveTools.py: Additional spectral parameters are not valid for the %s spectrum' %spectName)
                sys.exit(1)
        

        self.ai = np.sqrt(2.*returnRectangles(self.Si_Jm,self.fim))
        self.kDir = np.zeros((len(self.ki),3),)
        for ii in range(3):
             self.kDir[:,ii] = self.ki[:] * self.waveDir[ii] 
    def eta(self,x,y,z,t):
        """Free surface displacement

        :param x: floating point x coordinate
        :param t: time"""
        Eta=0.
        for ii in range(self.N):
            Eta+= eta_mode(x,y,z,t,self.kDir[ii],self.omega[ii],self.phi[ii],self.ai[ii])
        return Eta
#        return (self.ai*np.cos(2.0*pi*self.fi*t - self.ki*x + self.phi)).sum()

    def u(self,x,y,z,t,comp):
        """x-component of velocity

        :param x: floating point x coordinate
        :param z: floating point z coordinate (height above bottom)
        :param t: time
        """
        U=0.
        for ii in range(self.N):
            U+= vel_mode(x,y,z,t,self.kDir[ii], self.ki[ii],self.omega[ii],self.phi[ii],self.ai[ii],self.mwl,self.depth,self.g,self.vDir,comp)                
        return U        

class MultiSpectraRandomWaves(RandomWaves):
    """Generate a random wave timeseries from multiple spectra. 
    Same input parameters as RandomWaves class but they have to be all in lists with the same lenght as the spectra (except from g!)
    :param Nspectra, number of spectra
    """
    def __init__(self,
                 Nspectra,
                 Tp, # np array with 
                 Hs,
                 mwl,#m significant wave height
                 depth ,           #m depth
                 waveDir,
                 g,      #peak  frequency
                 N,
                 bandFactor,         #accelerationof gravity
                 spectName ,# random words will result in error and return the available spectra 
                 spectral_params, #JONPARAMS = {"gamma": 3.3, "TMA":True,"depth": depth} 
                 phi
                 ):
# Checking length of arrays / lists to be equal to NSpectra
        try:
            if (len(Tp) != Nspectra) or (len(Hs) != Nspectra) or (len(waveDir) != Nspectra) or \
               (len(N) != Nspectra) or (len(bandFactor) != Nspectra) or \
               (len(spectName) != Nspectra) or (len(spectral_params) != Nspectra) or(len(phi) != Nspectra):

                logEvent('WaveTools.py: Parameters passed in MultiSpectraRandomWaves must be in array or list form with length Nspectra  ')
                sys.exit(1)
               
        except:
            logEvent('WaveTools.py: Parameters passed in MultiSpectraRandomWaves must be in array or list form with length Nspectra  ')
            sys.exit(1)
        # Initialize numpy arrays for complete reconstruction
        self.Nall = 0 
        for nn in N:
            self.Nall+=nn
        

        self.omegaM = np.zeros(self.Nall,float)
        self.kiM = np.zeros(self.Nall,float)
        self.aiM = np.zeros(self.Nall,float)
        self.kDirM = np.zeros((self.Nall,3),float)
        self.phiM= np.zeros(self.Nall,float)


        NN = 0
        for kk in range(Nspectra):
            logEvent("WaveTools.py: Reading spectra No %s" %kk)
            NN1 = NN
            NN +=N[kk]
            RandomWaves.__init__(self,
                                 Tp[kk], # np array with 
                                 Hs[kk],
                                 mwl,#m significant wave height
                                 depth,           #m depth
                                 waveDir[kk],
                                 g,      #peak  frequency
                                 N[kk],
                                 bandFactor[kk],         #accelerationof gravity
                                 spectName[kk],# random words will result in error and return the available spectra 
                                 spectral_params[kk], #JONPARAMS = {"gamma": 3.3, "TMA":True,"depth": depth} 
                                 phi[kk]
                             )
            self.omegaM[NN1:NN] = self.omega
            self.kiM[NN1:NN] = self.ki
            self.aiM[NN1:NN] = self.ai
            self.kDirM[NN1:NN,:] =self.kDir[:,:]
            self.phiM[NN1:NN] = self.phi
        

    def eta(self,x,y,z,t):
        """Free surface displacement

        :param x: floating point x coordinate
        :param t: time"""
        Eta=0.
        for ii in range(self.Nall):
            Eta+= eta_mode(x,y,z,t,self.kDirM[ii],self.omegaM[ii],self.phiM[ii],self.aiM[ii])
        return Eta
#        return (self.ai*np.cos(2.0*pi*self.fi*t - self.ki*x + self.phi)).sum()

    def u(self,x,y,z,t,comp):
        """x-component of velocity

        :param x: floating point x coordinate
        :param z: floating point z coordinate (height above bottom)
        :param t: time
        """
        U=0.
        for ii in range(self.Nall):
            U+= vel_mode(x,y,z,t,self.kDirM[ii], self.kiM[ii],self.omegaM[ii],self.phiM[ii],self.aiM[ii],self.mwl,self.depth,self.g,self.vDir,comp)                
        return U        



class DirectionalWaves(RandomWaves):
    def __init__(self,
                 M,  #half bin of frequencies
                 Tp, # np array with 
                 Hs, # 
                 mwl,#m significant wave height
                 depth ,           #m depth
                 waveDir0,  # Lead direction
                 g,      #peak  frequency
                 N,    # Number of frequencies
                 bandFactor,         #accelerationof gravity
                 spectName ,# random words will result in error and return the available spectra 
                 spreadName ,# random words will result in error and return the available spectra 
                 spectral_params = None, #JONPARAMS = {"gamma": 3.3, "TMA":True,"depth": depth} 
                 spread_params = None, #JONPARAMS = {"gamma": 3.3, "TMA":True,"depth": depth}\ 
                 phi=None, # phi must be an (2*M+1)*N numpy array
                 phiSymm = False # When true, phi[-pi/2,0] is symmetric to phi[0,pi/2]
                 ):   
        validSpread = [cos2s,mitsuyasu]
        spread_fun =  loadExistingFunction(spreadName, validSpread)
        self.M = M
        self.Mtot = 2*M+1
        self.waveDir0 = setDirVector(waveDir0)
        self.vDir = setVertDir(g) 


 # Loading Random waves to get the frequency array the wavelegnths and the frequency spectrum
        RandomWaves.__init__(self,
                             Tp, # np array with 
                             Hs,
                             mwl,#m significant wave height
                             depth,           #m depth
                             self.waveDir0,
                             g,      #peak  frequency
                             N,
                             bandFactor,         #accelerationof gravity
                             spectName,# random words will result in error and return the available spectra 
                             spectral_params, #JONPARAMS = {"gamma": 3.3, "TMA":True,"depth": depth} 
                             phi = None 
        )

       
        
        # Directional waves propagate usually in a plane -90 to 90 deg with respect to the direction vector, normal to the gavity direction. Rotating the waveDir0 vector around the g vector to produce the directional space
        from SpatialTools import rotation3D
        self.thetas = np.linspace(-pi/2,pi/2,2*M+1)
        self.dth = (self.thetas[1] - self.thetas[0])
        self.waveDirs = np.zeros((2*M+1,3),)
        self.phiDirs = np.zeros((2*M+1,N),)
        self.aiDirs = np.zeros((2*M+1,N),)
        

        temp_array = np.zeros((1,3),)
        temp_array[0,:] = waveDir0
        directions = range(0,self.Mtot)

# initialising wave directions
        for rr in directions: 
            theta = self.thetas[rr]            
            self.waveDirs[rr,:] = rotation3D(temp_array,theta,self.vDir)[0,:]
            self.waveDirs[rr,:]=setDirVector( self.waveDirs[rr,:])


# Initialising phasing
        if phi == None:
            self.phiDirs = 2.0*pi*np.random.rand(self.Mtot,self.fi.shape[0])
        elif np.shape(phi) == (2*M+1,self.fi.shape[0]):
            self.phiDirs = phi
        else:
            logEvent("WaveTools.py: phi in DirectionalWaves class must be given either as None or as a list with 2*M + 1 numpy arrays with length N")
            sys.exit(1)
            
        if (phiSymm):
            self.phiDirs[:self.M:1] = self.phiDirs[self.M+1::-1]
            
            


        self.theta_m = reduceToIntervals(self.thetas,self.dth)        
        if (spread_params == None):
            self.Si_Sp = spread_fun(self.theta_m,self.fim)
        else:
            try:
                self.Si_Sp = spread_fun(self.theta_m,self.fim, **spread_params)
            except:
                logEvent('WaveTools.py: Additional spread parameters are not valid for the %s spectrum' %spectName)
                sys.exit(1)

        # Setting amplitudes 
        #Normalising the spreading function
        freq = range(0,self.N)
    # Normalising integral over all frequencies
        for ii in freq:            
            self.Si_Sp[:,ii] = normIntegral(self.Si_Sp[:,ii],self.theta_m)
            self.Si_Sp[:,ii]*= self.Si_Jm[ii] 
    # Creating amplitudes spectrum
        self.aiDirs[:] = np.sqrt(2.*returnRectangles3D(self.Si_Sp,self.theta_m,self.fim))
    def eta(self,x,y,z,t):
        """Free surface displacement

        :param x: floating point x coordinate
        :param t: time"""
        Eta=0.
        for jj in range(self.Mtot):
            for ii in range(self.N):
                kDiri = self.waveDirs[jj]*self.ki[ii]
                Eta+= eta_mode(x,y,z,t,kDiri,self.omega[ii],self.phiDirs[jj,ii],self.aiDirs[jj,ii])
        return Eta
#        return (self.ai*np.cos(2.0*pi*self.fi*t - self.ki*x + self.phi)).sum()

    def u(self,x,y,z,t,comp):
        """x-component of velocity

        :param x: floating point x coordinate
        :param z: floating point z coordinate (height above bottom)
        :param t: time
        """
        U=0.
        for jj in range(self.Mtot):
            for ii in range(self.N):
                kDiri = self.waveDirs[jj]*self.ki[ii]
                U+= vel_mode(x,y,z,t,kDiri, self.ki[ii],self.omega[ii],self.phiDirs[jj,ii],self.aiDirs[jj,ii],self.mwl,self.depth,self.g,self.vDir,comp)                
        return U        
     


            
                

        

class TimeSeries:
    """Generate a time series by using spectral windowing method.
    :param timeSeriesFile: Time series file name
    :param skiprows: How many rows to skip while reading time series
    :param  depth: depth [L]
    :param peakFrequency: expected peak frequency
    :param N: number of frequency bins [-]
    :param Nwaves: Number of waves per window (Approx)
    :param mwl: mean water level [L]
    :param waveDir: wave Direction vector
    """

    def __init__(self,
                 timeSeriesFile, # e.g.= "Timeseries.txt",
                 skiprows,
                 timeSeriesPosition,
                 depth  ,
                 N ,          #number of frequency bins
                 mwl ,        #mean water level
                 waveDir, 
                 g,
                 rec_direct = True,
                 wind_params = None #If rec_direct = False then wind_params = {"Nwaves":Nwaves,"Window":wind_fun}
                 ):

        # Setting the depth
        self.depth = depth
        self.rec_direct = rec_direct
        # Number of wave components
        self.N = N
        self.Nwaves = None
        # Position of timeSeriesFile
        if(len(timeSeriesPosition)==3):
            self.x0 = timeSeriesPosition[0]
            self.y0 = timeSeriesPosition[1]
            self.z0 = timeSeriesPosition[2]
        else:
            logEvent("WaveTools.py: Location vector for timeSeries must have three-components",level=0)
            sys.exit(1)
            

        # Mean water level
        self.mwl = mwl
        # Wave direction
        self.waveDir = setDirVector(waveDir)
        # Gravity
        self.g = np.array(g)
        # Derived variables
        # Gravity magnitude
        self.gAbs = sqrt(sum(g * g))
        # Definition of gravity direction
        self.vDir = setVertDir(g)
        dirCheck(self.waveDir,self.vDir)
        #Reading time series
        filetype = timeSeriesFile[-4:]
        logEvent("WaveTools.py: Reading timeseries from %s file: %s" % (filetype,timeSeriesFile),level=0)
        fid = open(timeSeriesFile,"r")
        if (filetype !=".txt") and (filetype != ".csv"):
                logEvent("WaveTools.py: File %s must be given in .txt or .csv format" % (timeSeriesFile),level=0)
                sys.exit(1)
        elif (filetype == ".csv"):
            tdata = np.loadtxt(fid,skiprows=skiprows,delimiter=",")
        else:
            tdata = np.loadtxt(fid,skiprows=skiprows)
        fid.close()
        #Checks for tseries file
        # Only 2 columns: time & eta
        ncols = len(tdata[0,:])
        if ncols != 2:
            logEvent("WaveTools.py: Timeseries file (%s) must have only two columns [time, eta]" % (timeSeriesFile),level=0)
            sys.exit(1)
        time_temp = tdata[:,0]
        self.dt = (time_temp[-1]-time_temp[0])/(len(time_temp)-1)



        # If necessary, perform interpolation
        doInterp = False
        for i in range(1,len(time_temp)):
            dt_temp = time_temp[i]-time_temp[i-1]
        #check if time is at first column
            if time_temp[i]<=time_temp[i-1]:
                logEvent("WaveTools.py:  Found not consistent time entry between %s and %s row in %s file. Time variable must be always at the first column of the file and increasing monotonically" %(i-1,i,timeSeriesFile) )
                sys.exit(1)
        #check if sampling rate is constant
            if abs(dt_temp-self.dt)/self.dt <= 1e-10:
                doInterp = True
        if(doInterp):
            logEvent("WaveTools.py: Not constant sampling rate found, proceeding to signal interpolation to a constant sampling rate",level=0)
            self.time = np.linspace(time_temp[0],time_temp[-1],len(time_temp))
            self.eta = np.interp(self.time,time_temp,tdata[:,1])
        else:
            self.time = time_temp
            self.eta = tdata[:,1]

        self.t0  = self.time[0]        
        # Remove mean level from raw data
        self.eta -= np.mean(self.eta)
        # Filter out first 2.5 % and last 2.5% to make the signal periodic
        self.eta *=costap(len(self.time),cutoff=0.025)
        # clear tdata from memory
        del tdata
        # Calculate time lenght
        self.tlength = (self.time[-1]-self.time[0])
        # Matrix initialisation
        self.windows_handover = []
        self.windows_rec = []





        # Direct decomposition of the time series for using at reconstruct_direct
        if (self.rec_direct):
            Nf = self.N
            self.nfft=len(self.time)
            logEvent("WaveTools.py: performing a direct series decomposition")
            self.decomp = decompose_tseries(self.time,self.eta)
            self.ai = self.decomp[1]
            ipeak = np.where(self.ai == max(self.ai))[0][0]
            imax = min(ipeak + Nf/2,len(self.ai))
            imin = max(0,ipeak - Nf/2)
            self.ai = self.ai[imin:imax]
            self.omega = self.decomp[0][imin:imax]
            self.phi = self.decomp[2][imin:imax]
            self.ki = dispersion(self.omega,self.depth,g=self.gAbs)
            self.Nf = imax - imin
            self.setup = self.decomp[3]
            self.kDir = np.zeros((len(self.ki),3),"d")
            for ii in range(len(self.ki)):
                self.kDir[ii,:] = self.ki[ii]*self.waveDir[:]


                # Spectral windowing
        else:
            if (wind_params==None):
                logEvent("WaveTools.py: Set parameters for spectral windowing. Argument wind_params must be a dictionary")
                sys.exit(1)
            try:
                self.Nwaves = wind_params["Nwaves"]
            except:
                logEvent("WaveTools.py: Dictionary key 'Nwaves' (waves per window) not found in wind_params dictionary")
                sys.exit(1)
            try:           
                windowName = wind_params["Window"]
            except:
                logEvent("WaveTools.py: Dictionary key 'Window' (windo function type) not found in wind_params dictionary")
                sys.exit(1)

            validWindows = [costap, tophat]
            wind_fun =  loadExistingFunction(windowName, validWindows) 
            logEvent("WaveTools.py: performing series decomposition with spectral windows")
            # Portion of overlap, compared to window time
            try:
                self.Nwaves = wind_params["Overlap"]            
            except:
                overlap = 0.25

            try:
                self.Nwaves = wind_params["Cutoff"]            
            except:
                cutoff= 0.1
            # Portion of window filtered with the Costap filter
            # Setting the handover time, either at the middle of the overlap or just after the filter
            Handover = min(overlap - 1.1 *cutoff,  overlap / 2.)
            # setting the window duration (approx.). Twindow = Tmean * Nwaves = Tpeak * Nwaves /1.1
            self.Twindow =  self.Nwaves / (1.1 * self.peakFrequency )
#            print self.Twindow
            #Settling overlap 25% of Twindow
            self.Toverlap = overlap * self.Twindow
            #Getting the actual number of windows
            # (N-1) * (Twindow - Toverlap) + Twindow = total time
            self.Nwindows = int( (self.tlength -   self.Twindow ) / (self.Twindow - self.Toverlap) ) + 1
            # Correct Twindow and Toverlap for duration and integer number of windows
            self.Twindow = self.tlength/(1. + (1. - overlap)*(self.Nwindows-1))
            self.Toverlap = overlap*self.Twindow
            logEvent("WaveTools.py: Correcting window duration for matching the exact time range of the series. Window duration correspond to %s waves approx." %(self.Twindow * 1.1* self.peakFrequency) )
            diff = (self.Nwindows-1.)*(self.Twindow -self.Toverlap)+self.Twindow - self.tlength
            logEvent("WaveTools.py: Checking duration of windowed time series: %s per cent difference from original duration" %(100*diff) )
            logEvent("WaveTools.py: Using %s windows for reconstruction with %s sec duration and %s per cent overlap" %(self.Nwindows, self.Twindow,100*overlap) )
# Setting where each window starts and ends
            for jj in range(self.Nwindows):
                span = np.zeros(2,"d")
                tfirst = self.time[0] + self.Twindow
                tlast = self.time[-1] - self.Twindow
                if jj == 0:
                    ispan1 = 0
                    ispan2 = np.where(self.time> tfirst)[0][0]
                elif jj == self.Nwindows-1:
                    ispan1 = np.where(self.time > tlast)[0][0]
                    ispan2 = len(self.time)-1
                else:
                    tstart = self.time[ispan2] - self.Toverlap
                    ispan1 = np.where(self.time > tstart)[0][0]
                    ispan2 = np.where(self.time > tstart + self.Twindow )[0][0]
                span[0] = ispan1
                span[1] = ispan2
# Storing time series in windows and handover times
                self.windows_handover.append( self.time[ispan2] - Handover*self.Twindow )
                self.windows_rec.append(np.array(zip(self.time[ispan1:ispan2],self.eta[ispan1:ispan2])))
# Decomposing windows to frequency domain
            self.decompose_window = []
#            style = "k-"
#            ii = 0
            for wind in self.windows_rec:
                self.nfft=len(wind[:,0])
                wind[:,1] *=wind_fun(self.nfft,cutoff = cutoff)
                decomp = decompose_tseries(wind[:,0],wind[:,1],self.nfft,self.N,ret_only_freq=0)
                self.decompose_window.append(decomp)
#                if style == "k-":
#                    style = "kx"
#                else:
#                    style ="k-"
#                plt.plot(wind[:,0],wind[:,1],style)
#                plt.plot(self.time,self.eta,"bo",markersize=2)
#                plt.plot([self.windows_handover[ii],self.windows_handover[ii]] , [-1000,1000],"b--")
#                ii+=1
#            plt.ylim(-1,2)
#            plt.grid()
#            plt.savefig("rec.pdf")
#            self.Twindow = self.Npw*self.dt
#            self.Noverlap = int(self.Npw *0.25)

    def etaDirect(self,x,y,z,t):
        """Free surface displacement
        :param x: floating point x coordinate
        :param t: time"""
        Eta=0.        
        for ii in range(self.Nf):
            Eta+= eta_mode(x-self.x0,y-self.y0,z-self.z0,t-self.t0,self.kDir[ii],self.omega[ii],self.phi[ii],self.ai[ii])
        return Eta

    def uDirect(self,x,y,z,t,comp):
        """x-component of velocity

        :param x: floating point x coordinate
        :param z: floating point z coordinate (height above bottom)
        :param t: time
        """
        U=0.
        for ii in range(self.N):
            U+= vel_mode(x-self.x0,y-self.y0,z-self.z0,t-self.t0,self.kDir[ii],self.omega[ii],self.phi[ii],self.ai[ii],self.mwl,self.depth,self.g,self.vDir,comp)                
        return U        


    def reconstruct_window(self,x,y,z,t,Nf,var="eta",ss = "x"):
        "Direct reconstruction of a timeseries"
#        if self.rec_direct==True:
#            logEvent("WaveTools.py: While attempting  reconstruction in windows, wrong input for rec_direct found (should be set to False)",level=0)
#            logEvent("Stopping simulation",level=0)
#            exit(1)


        #Tracking the time window (spatial coherency not yet implemented)
        #Nw = 2
        if t-self.time[0] >= 0.875*self.Twindow:
            Nw = min(int((t-self.time[0] - 0.875*self.Twindow)/(self.Twindow - 2. * 0.125 * self.Twindow)) + 1, self.Nwindows-1)
            if t-self.time[0] < self.windows_handover[Nw-1] - self.time[0]:
                Nw-=1
        else:
            Nw = 0

        print t,Nw, self.windows_handover[Nw]

        tinit = self.windows_rec[Nw][0,0]
#        thand = self.windows_handover[Nw]
#        tinit  = self.windows_rec[Nw][0,0]
#       if t >= thand[1]:
#           Nw = min(Nw+1, 3)


        ai = self.decompose_window[Nw][1]
        ipeak = np.where(ai == max(ai))[0][0]
        imax = min(ipeak + Nf/2,len(ai))
        imin = max(0,ipeak - Nf/2)
        ai = ai[imin:imax]
        omega = self.decompose_window[Nw][0][imin:imax]
        phi = self.decompose_window[Nw][2][imin:imax]
        setup = self.decompose_window[Nw][3]
        ki = dispersion(omega,self.depth,g=self.gAbs)
        kDir = np.zeros((len(ki),3),"d")
        Nf = len(omega)
        for ii in range(len(ki)):
            kDir[ii,:] = ki[ii]*self.waveDir[:]
        if var=="eta":
            Eta=setup
            for ii in range(Nf):
                Eta+=ai[ii]*cos(x*kDir[ii,0]+y*kDir[ii,1]+z*kDir[ii,2] - omega[ii]*(t-tinit) - phi[ii])
            if (Nw <10000):
                return Eta
            else:
                return 0.
        if var=="U":
            UH=0.
            UV=0.
            for ii in range(Nf):
                UH+=ai[ii]*omega[ii]*cosh(ki[ii]*(self.Z(x,y,z)+self.depth))*cos(x*kDir[ii,0]+y*kDir[ii,1]+z*kDir[ii,2] - omega[ii]*t - phi[ii])/sinh(ki[ii]*self.depth)
                UV+=ai[ii]*omega[ii]*sinh(ki[ii]*(self.Z(x,y,z)+self.depth))*sin(x*kDir[ii,0]+y*kDir[ii,1]+z*kDir[ii,2] - omega[ii]*t - phi[ii])/sinh(ki[ii]*self.depth)
#waves(period = 1./self.fi[ii], waveHeight = 2.*self.ai[ii],mwl = self.mwl, depth = self.d,g = self.g,waveDir = self.waveDir,wavelength=self.wi[ii], phi0 = self.phi[ii]).u(x,y,z,t)
            Vcomp = {
                    "x":UH*self.waveDir[0] + UV*self.vDir[0],
                    "y":UH*self.waveDir[1] + UV*self.vDir[1],
                    "z":UH*self.waveDir[2] + UV*self.vDir[2],
                    }
            return Vcomp[ss]



