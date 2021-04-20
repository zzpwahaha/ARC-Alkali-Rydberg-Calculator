# -*- coding: utf-8 -*-

"""
    This module provides calculations of single-atom properties.

    Included calculations are Stark maps, level plot visualisations,
    lifetimes and radiative decays.

"""

from __future__ import print_function

from .alkali_atom_functions import printStateString, _EFieldCoupling, printStateLetter, printStateStringLatex
import datetime
import sqlite3
import matplotlib
from matplotlib.colors import LinearSegmentedColormap
from math import sqrt
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
import numpy as np
import re
from .wigner import Wigner6j, CG
from scipy.constants import physical_constants, pi, epsilon_0, hbar
from scipy.constants import k as C_k
from scipy.constants import c as C_c
from scipy.constants import h as C_h
from scipy.constants import e as C_e
from scipy.constants import m_e as C_m_e
from scipy.optimize import curve_fit
from scipy import interpolate

# for matrices
from numpy.linalg import eigh

from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh
from scipy.special import sph_harm

import sys
if sys.version_info > (2,):
    xrange = range


sqlite3.register_adapter(np.float64, float)
sqlite3.register_adapter(np.float32, float)
sqlite3.register_adapter(np.int64, int)
sqlite3.register_adapter(np.int32, int)


def Ylm(l, m, theta, phi):
    return sph_harm(m, l, phi, theta)

class Wavefunction:
    r"""
        Calculates and plots electron wavefunctions.

       For an example see `wavefunction plotting example snippet`_.

       .. _`wavefunction plotting example snippet`:
           ./ARC_3_0_introduction.html#Wavefunction-calculations-for-Alkali-atom-Rydberg-states

        Args:
            atom: atom type considered (for example :obj:`Rubidum87()`)
            basisStates (array): array of states in fine basis that contribute\
                to the state whose wavefunction is requested.
                :math:`[[n_1, \ell_1, j_1, m_{j1}], ...]` For efficient
                calculation **do not** pass all the possible basis states, but
                just the once that have significant contribution to the
                reqested state.
            coefficients (array): array `[c1, ...]` of complex coefficents
                :math:`c_i = \langle \psi_i |\psi\rangle` corresponding to
                decomposition of required state :math:`|\psi\rangle` on basis
                states :math:`|\psi_i \rangle` .
    """

    def __init__(self, atom, basisStates, coefficients):
        # n, l, j, mj
        self.atom = atom
        if (len(basisStates) == 0 or len(basisStates[0]) != 4
                or len(basisStates) != len(coefficients)):
            raise ValueError("basisStates should be defined as array of"
                             "states in fine basis [[n1, l1, j1, mj1], ... ]"
                             "contributing to the required states "
                             "(do not use unecessarily whole basis) "
                             "while coefficients corresponding to decomposition "
                             "of requested state on these basis state "
                             "should be given as"
                             "separete array [c1, ...]")
        self.basisStates = basisStates
        self.coef = coefficients
        self.basisWavefunctions = []

        for state in self.basisStates:
            n = state[0]
            l = state[1]
            j = state[2]

            # calculate radial wavefunction
            step = 0.001
            r, rWavefunc = atom.radialWavefunction(
                l, 0.5, j,
                self.atom.getEnergy(n, l, j) / 27.211,
                self.atom.alphaC**(1 / 3.0),
                2.0 * n * (n + 15.0), step)
            suma = np.trapz(rWavefunc**2, x=r)
            rWavefunc = rWavefunc / (sqrt(suma))

            self.basisWavefunctions.append(
                interpolate.interp1d(r, rWavefunc,
                                    bounds_error=False,
                                    fill_value=(0,0))
                )

    def getRtimesPsiSpherical(self, theta, phi, r):
        r"""
            Calculates list of :math:`r \cdot \psi_{m_s} (\theta, \phi, r)`

            At point defined by spherical coordinates, returns list of
            :math:`r \cdot \psi_{m_s} (\theta, \phi, r)`
            wavefunction values for different electron spin projection
            values :math:`m_s`.

            Coordinates are defined relative to atomic core.

            Args:
                theta (float): polar angle (angle between :math:`z` axis and
                    vector pointing towards selected point)
                    (in units of radians).
                phi (float): azimuthal angle (angle between :math:`x` axis and
                    projection at :math:`x-y` plane of vector pointing towards
                    selected point) (in units of radians).
                r (float): distance between coordinate origin and selected
                    point. (in atomic units of Bohr radius :math:`a_0`)

            Returns:
                list of complex values corresponding to
                :math:`\psi_{m_s} (\theta, \phi, r)` for different
                spin states :math:`m_s` contributing to the state in **decreasing**
                order of :math:`m_s`. For example, for :obj:`arc.AlkaliAtom`
                returns :math:`r \cdot \psi_{m_s=+1/2} (\theta, \phi, r)` and
                :math:`r \cdot \psi_{m_s=-1/2} (\theta, \phi, r) `.
                )`
        """

        wfElectronP = 0+0j  # electron spin +1/2
        wfElectronM = 0+0j  # electron spin -1/2

        for i, state in enumerate(self.basisStates):
            l = state[1]
            j = state[2]
            mj = state[3]
            if abs(mj - 0.5) - 0.1 < l:
                wfElectronP += CG(l, mj-0.5, 0.5, +0.5, j, mj) \
                               * Ylm(l, mj-0.5, theta, phi)\
                               * self.basisWavefunctions[i](r) \
                               * self.coef[i]
            if abs(mj + 0.5) - 0.1 < l:
                wfElectronM += CG(l, mj+0.5, 0.5, -0.5, j, mj) \
                               * Ylm(l, mj+0.5, theta, phi) \
                               * self.basisWavefunctions[i](r) \
                               * self.coef[i]
        return wfElectronP, wfElectronM

    def getRtimesPsi(self, x, y, z):
        r"""
            Calculates list of :math:`r \cdot \psi_{m_s} (x, y, z)`

            At a point defined by Cartesian coordinates returns list of
            :math:`r \cdot \psi_{m_s} (x, y, z)`
            wavefunction values for different
            electron spin projection values :math:`m_s`.

            Args:
                x (float): Cartesian coordinates of selected point,
                    relative to the atom core.
                    (in atomic units of Bohr radius :math:`a_0`)
                y (float): Cartesian coordinates of selected point,
                    relative to the atom core.
                    (in atomic units of Bohr radius :math:`a_0`)
                z (float): Cartesian coordinates of selected point,
                    relative to the atom core.
                    (in atomic units of Bohr radius :math:`a_0`)

            Returns:
                list of complex values corresponding to
                :math:`r \cdot \psi_{m_s} (\theta, \phi, r)` for different
                spin states :math:`m_s` contributing to the state in
                **decreasing** order of :math:`m_s`.
                For example, for :obj:`arc.AlkaliAtom`
                returns :math:`r \cdot \psi_{m_s=+1/2} (\theta, \phi, r)` and
                :math:`r \cdot \psi_{m_s=-1/2} (\theta, \phi, r)` .
                )`, where :math:`r=\sqrt{x^2+y^2+z^2}`.
        """
        theta = np.arctan2((x**2 + y**2)**0.5, z)
        phi = np.arctan2(y, x)
        r = np.sqrt(x**2 + y**2 + z**2)
        return self.getRtimesPsiSpherical(theta, phi, r)

    def getPsi(self, x, y, z):
        r"""
            Calculates list of :math:`\psi_{m_s} (x,y,z)`

            At point define by Cartesian coordinates returns list of
            :math:`\psi_{m_s} (x,y,z)` wavefunction values corresponding
            to different electron spin projection values :math:`m_s`.

            Args:
                x (float): Cartesian coordinates of selected point,
                    relative to the atom core.
                    (in atomic units of Bohr radius :math:`a_0`)
                y (float): Cartesian coordinates of selected point,
                    relative to the atom core.
                    (in atomic units of Bohr radius :math:`a_0`)
                z (float): Cartesian coordinates of selected point,
                    relative to the atom core.
                    (in atomic units of Bohr radius :math:`a_0`)

            Returns:
                list of complex values corresponding to
                :math:`\psi_{m_s} (\theta, \phi, r)` for different
                spin states :math:`m_s` contributing to the state in
                **decreasing** order of :math:`m_s`.
                For example, for :obj:`arc.AlkaliAtom`
                returns :math:`\psi_{m_s=+1/2} (\theta, \phi, r)` and
                :math:`\psi_{m_s=-1/2} (\theta, \phi, r)` .
                )`.
        """
        r = np.sqrt(x * x + y * y + z * z)
        return self.getRtimesPsi(x, y, z) / r

    def getRtimesPsiSquaredInPlane(self,
                                   plane="x-z",
                                   pointsPerAxis=150,
                                   axisLength=None,
                                   units="atomic"
                                   ):
        r"""
        Calculates :math:`|r \cdot \psi|^2` on a mesh in a given plane.

        Args:
            plane (str): optiona, set's calculation plane to `'x-y'` or
                `'x-z'`. Default value `'x-y'`
            pointsPerAxis (int): optional, a number of mesh points per
                Carthesian axis. Default value of 150, gives a mesh with total
                size of :math:`150 \times 150 = 22500` points.
            axisLength (float): optional, length of the square in the selected
                plane on which wavefunction will be calculated. By default it
                is largw enough to fit the whole wavefunction
                (in atomic units of Bohr radius :math:`a_0`).
            units (str): optional, units of length in which calculated mesh
                will be **returned** (note that `axisLength` is on the other
                hand always in atomi units.). Supported values are
                `'atomic'` or `'nm'`. Default value `'atomic'` .

        Returns:
            meshCoordinate1, meshCoordinate2 and
            :math:`|r \cdot \psi|^2 = \sum_{m_s} |r \cdot \psi_{m_s}|^2`,
            where sum is over possible electron spin projection values
            :math:`m_s`.

        """
        if axisLength is None:
            nMax = 1
            for state in self.basisStates:
                nMax = max(nMax, state[0])
            axisLength = 2.0 * 2.0 * nMax * (nMax + 15.0)

        coord1 = np.linspace(- axisLength / 2., axisLength / 2., pointsPerAxis)
        coord2 = np.linspace(- axisLength / 2., axisLength / 2., pointsPerAxis)
        meshCoord1, meshCoord2 = np.meshgrid(coord1, coord2)

        coord = []
        if (plane == "x-z"):
            coord = [meshCoord1, 0, meshCoord2]
        elif (plane == "x-y"):
            coord = [meshCoord1, meshCoord2, 0]
        else:
            raise ValueError("Only 'x-y' and 'x-z' planes are supported.")

        wfP, wfM = self.getRtimesPsi(*coord)

        # change units
        if units == "nm":
            scale = physical_constants["Bohr radius"][0]*1e9
            meshCoord1 *= scale
            meshCoord2 *= scale
            wfP /= scale
            wfM /= scale
        elif units == "atomic":
            pass
        else:
            raise ValueError("Only 'atomic' (a_0) and 'nm' are recognised"
                             "as possible units. Received: %s" % units)

        f = np.power(np.abs(wfP), 2) + np.power(np.abs(wfM), 2)
        return meshCoord1, meshCoord2, f


    def plot2D(self,
               plane="x-z",
               pointsPerAxis=150,
               axisLength = None,
               units="atomic",
               colorbar=True, labels=True):
        r"""
        2D colour plot of :math:`|r \cdot \psi|^2` wavefunction in a
        requested plane.

        Args:
            plane (str): optiona, set's calculation plane to `'x-y'` or `'x-z'`.
                Default value `'x-y'`
            pointsPerAxis (int): optional, a number of mesh points per Carthesian
                axis. Default value of 150, gives a mesh with total size of
                :math:`150 \times 150 = 22500` points.
            axisLength (float): optional, length of the square in the selected
                plane on which wavefunction will be calculated. By default it
                is large enough to fit the whole wavefunction
                (in atomic units of Bohr radius :math:`a_0`).
            units (str): optional, units of length in which calculated mesh
                will be **returned** (note that `axisLength` is on the other
                hand always in atomi units.). Supported values are
                `'atomic'` or `'nm'`. Default value `'atomic'` .
            colorbar (bool): optional, determens if the colour bar scale of
                should be shown. Default value is `True`.
            labels (bool): optional, determines if the labels on the axis
                of the plot should be shown. Default value is `True`.

        Returns:
            :obj:`matplotlib.pyplot.figure` object with a requested plot. Use `show()`
            method to see figure.

        """


        x,y,f = self.getRtimesPsiSquaredInPlane(plane=plane,
                                               pointsPerAxis=pointsPerAxis,
                                               axisLength=axisLength,
                                               units=units)

        fig = plt.figure(figsize=(6,4))
        ax = fig.add_subplot(1,1,1)
        cp = ax.pcolor(x, y, f,
                       vmin=0, vmax=f.max(), cmap='viridis')


        if labels:
            if units=="atomic":
                unitLabel = r"$a_0$"
            else:
                unitLabel = "nm"
            if plane=="x-y":
                plt.xlabel(r"$x$ (%s)" % unitLabel)
                plt.ylabel(r"$y$ (%s)" % unitLabel)
            elif plane=="x-z":
                plt.xlabel(r"$x$ (%s)" % unitLabel)
                plt.ylabel(r"$z$ (%s)" % unitLabel)
            else:
                raise ValueError("Only 'atomic' (a_0) and 'nm' are recognised"
                             "as possible units. Received: %s" % units)
        ax.set_aspect('equal', 'box')
        if colorbar:
            cb = fig.colorbar(cp)
            cb.set_label(r'$|r\cdot\psi(x,y,z)|^2$')  # NOTE: change label if plotting Imaginart part!
        return fig
    # return figure

    def plot3D(self,
               plane="x-z",
               pointsPerAxis=150,
               axisLength = None,
               units="atomic",
               labels=True):
        r"""
        3D colour surface plot of :math:`|r \cdot \psi|^2` wavefunction in a
        requested plane.

        Args:
            plane (str): optiona, set's calculation plane to `'x-y'` or `'x-z'`.
                Default value `'x-y'`
            pointsPerAxis (int): optional, a number of mesh points per Carthesian
                axis. Default value of 150, gives a mesh with total size of
                :math:`150 \times 150 = 22500` points.
            axisLength (float): optional, length of the square in the selected
                plane on which wavefunction will be calculated. By default it
                is large enough to fit the whole wavefunction
                (in atomic units of Bohr radius :math:`a_0`).
            units (str): optional, units of length in which calculated mesh
                will be **returned** (note that `axisLength` is on the other
                hand always in atomi units.). Supported values are
                `'atomic'` or `'nm'`. Default value `'atomic'` .
            labels (bool): optional, determines if the labels on the axis
                of the plot should be shown. Default value is `True`.

        Returns:
            :obj:`matplotlib.figure` object with a requested plot. Use `show()`
            method to see figure.

        """


        x, y, f = self.getRtimesPsiSquaredInPlane(plane=plane,
                                                  pointsPerAxis=pointsPerAxis,
                                                  axisLength=axisLength,
                                                  units=units)
        fig = plt.figure(figsize=(6,4))
        ax = fig.gca(projection='3d')
        ax.view_init(40, -35)

        # Plot the surface.

        ax.plot_surface(x, y, f, cmap='Reds',
                               vmin=0, vmax=f.max(),
                               linewidth=0, antialiased=False,
                               rstride=1, cstride=1)
        ax.plot_wireframe(x, y, f,
                          rstride=10, cstride=10,
                          alpha=0.05, color="k")

        if labels:
            if units=="atomic":
                unitLabel = r"$a_0$"
            else:
                unitLabel = "nm"
            if plane=="x-y":
                plt.xlabel(r"$x$ (%s)" % unitLabel)
                plt.ylabel(r"$y$ (%s)" % unitLabel)
            elif plane=="x-z":
                plt.xlabel(r"$x$ (%s)" % unitLabel)
                plt.ylabel(r"$z$ (%s)" % unitLabel)
            else:
                raise ValueError("Only 'atomic' (a_0) and 'nm' are recognised"
                             "as possible units. Received: %s" % units)
        plt.xlim(x.min(),x.max())
        plt.ylim(y.min(),y.max())

        return fig


class StarkMap:
    """
        Calculates Stark maps for single atom in a field

        This initializes calculation for the atom of a given type. For details
        of calculation see Zimmerman [1]_. For a quick working example
        see `Stark map example snippet`_.

        Args:
            atom (:obj:`AlkaliAtom` or :obj:`DivalentAtom`): ={
                :obj:`arc.alkali_atom_data.Lithium6`,
                :obj:`arc.alkali_atom_data.Lithium7`,
                :obj:`arc.alkali_atom_data.Sodium`,
                :obj:`arc.alkali_atom_data.Potassium39`,
                :obj:`arc.alkali_atom_data.Potassium40`,
                :obj:`arc.alkali_atom_data.Potassium41`,
                :obj:`arc.alkali_atom_data.Rubidium85`,
                :obj:`arc.alkali_atom_data.Rubidium87`,
                :obj:`arc.alkali_atom_data.Caesium`,
                :obj:`arc.divalent_atom_data.Strontium88`,
                :obj:`arc.divalent_atom_data.Calcium40`
                :obj:`arc.divalent_atom_data.Ytterbium174` }
                Select the alkali metal for energy level
                diagram calculation

        Examples:
            State :math:`28~S_{1/2}~|m_j|=0.5` polarizability calculation

            >>> from arc import *
            >>> calc = StarkMap(Caesium())
            >>> calc.defineBasis(28, 0, 0.5, 0.5, 23, 32, 20)
            >>> calc.diagonalise(np.linspace(00.,6000,600))
            >>> print("%.5f MHz cm^2 / V^2 " % calc.getPolarizability())
            0.76705 MHz cm^2 / V^2

            Stark map calculation

            >>> from arc import *
            >>> calc = StarkMap(Caesium())
            >>> calc.defineBasis(28, 0, 0.5, 0.5, 23, 32, 20)
            >>> calc.diagonalise(np.linspace(00.,60000,600))
            >>> calc.plotLevelDiagram()
            >>> calc.showPlot()
            << matplotlib plot will open containing a Stark map >>

        Examples:
            **Advanced interfacing of Stark map calculations (StarkMap class)**
            Here we show one easy way to obtain the Stark matrix (from diagonal
            :obj:`mat1` and off-diagonal part :obj:`mat2` ) and basis states
            (stored in :obj:`basisStates` ), if this middle-product of the
            calculation is needed for some code build on top of the existing
            ARC package.

            >>> from arc import *
            >>> calc = StarkMap(Caesium())
            >>> calc.defineBasis(28, 0, 0.5, 0.5, 23, 32, 20)
            >>> # Now we have matrix and basis states, that we can used in our own code
            >>> # Let's say we want Stark map at electric field of 0.2 V/m
            >>> eField = 0.2 # V/m
            >>> # We can easily extract Stark matrix
            >>> # as diagonal matrix (state detunings)
            >>> #  + off-diagonal matrix (propotional to electric field)
            >>> matrix = calc.mat1+calc.mat2*eField
            >>> # and the basis states as array [ [n,l,j,mj] , ...]
            >>> basisStates = calc.basisStates
            >>> # you can do your own calculation now...

        References:
            .. [1] M. L. Zimmerman et.al, PRA **20**:2251 (1979)
                https://doi.org/10.1103/PhysRevA.20.2251

        .. _`Stark map example snippet`:
            ./Rydberg_atoms_a_primer.html#Rydberg-Atom-Stark-Shifts
    """

    def __init__(self, atom):

        self.atom = atom

        self.basisStates = []
        """
            List of basis states for calculation in the form [ [n,l,j,mj], ...].
            Calculated by :obj:`defineBasis` .
        """
        self.mat1 = []
        """
            diagonal elements of Stark-matrix (detuning of states) calculated by
            :obj:`defineBasis` in the basis :obj:`basisStates`.
        """
        self.mat2 = []
        """
            off-diagonal elements of Stark-matrix divided by electric
            field value. To get off diagonal elemements multiply this matrix
            with electric field value. Full Stark matrix is obtained as
            `fullStarkMatrix` = :obj:`mat1` + :obj:`mat2` *`eField`. Calculated by
            :obj:`defineBasis` in the basis :obj:`basisStates`.
        """
        self.indexOfCoupledState = []
        """
            Index of coupled state (initial state passed to :obj:`defineBasis`)
            in :obj:`basisStates` list of basis states
        """

        # finding energy levels
        self.eFieldList = []
        """
        Saves electric field (in units of V/m) for which energy levels are calculated

        See also:
            :obj:`y`, :obj:`highlight`, :obj:`diagonalise`
        """
        self.y = []  # eigenValues
        """
        `y[i]` is an array of eigenValues corresponding to the energies of the
        atom states at the electric field `eFieldList[i]`. For example `y[i][j]` is
        energy of the `j` eigenvalue (energy of the state) measured in
        cm :math:`{}^{-1}` relative to the ionization threshold.

        See also:
            :obj:`eFieldList`, :obj:`highlight`, :obj:`diagonalise`
        """
        self.highlight = [
        ]  # contribution of initial state there (overlap |<original state | given state>|^2)
        """
        `highlight[i]` is an array of values measuring highlighted feature in the
        eigenstates at electric field intensity `eFieldList[i]`. E.g. `highlight[i][j]`
        measures highlighted feature of the state with energy `y[i][j]` at electric
        field `eFieldList[i]`. What will be highlighted feature is defined in the
        call of :obj:`diagonalise` (see that part of documentation for details).

        See also:
            :obj:`eFieldList`, :obj:`y`, :obj:`diagonalise`
        """

        #: pointer towards matplotlib figure after :obj:`plotLevelDiagram`
        #: is called to create figure
        self.fig = 0
        #: pointer towards matplotlib figure axis after :obj:`plotLevelDiagram`
        #: is called to create figure
        self.ax = 0

        # values used for fitting polarizability, and fit
        self.fitX = []
        self.fitY = []
        self.fittedCurveY = []

        self.drivingFromState = [0, 0, 0, 0, 0]
        self.maxCoupling = 0.

        # STARK memoization
        self.eFieldCouplingSaved = False

        #: spin manifold in which we are working
        #: default value of 0.5 is correct for Alkaline Atoms. Otherwise it has
        #: to be specified when calling `defineBasis` as `s=0` or `s=1` for
        #: singlet and triplet states respectively
        self.s = 0.5

    def _eFieldCouplingDivE(self, n1, l1, j1, mj1, n2, l2, j2, mj2, s=0.5):
        # eFied coupling devided with E (witout actuall multiplication to getE)
        # delta(mj1,mj2') delta(l1,l2+-1)
        if ((abs(mj1 - mj2) > 0.1) or (abs(l1 - l2) != 1)):
            return 0

        # matrix element
        result = self.atom.getRadialMatrixElement(n1, l1, j1,
                                                  n2, l2, j2,
                                                  s=s) *\
            physical_constants["Bohr radius"][0] * C_e

        sumPart = self.eFieldCouplingSaved.getAngular(l1, j1, mj1,
                                                      l2, j2, mj2,
                                                      s=s)
        return result * sumPart

    def _eFieldCoupling(self, n1, l1, j1, mj1, n2, l2, j2, mj2, eField, s=0.5):
        return self._eFieldCouplingDivE(n1, l1, j1, mj1,
                                        n2, l2, j2, mj2,
                                        s=s) * eField

    def defineBasis(self, n, l, j, mj, nMin, nMax, maxL, Bz=0,
                    progressOutput=False, debugOutput=False, s=0.5):
        """
            Initializes basis of states around state of interest

            Defines basis of states for further calculation. :math:`n,l,j,m_j`
            specify state whose neighbourhood and polarizability we want
            to explore. Other parameters specify basis of calculations.
            This method stores basis in :obj:`basisStates`, while corresponding
            interaction matrix is stored in two parts. First part is diagonal
            electric-field independent part stored in :obj:`mat1`, while the
            second part :obj:`mat2` corresponds to off-diagonal elements that are
            propotional to electric field. Overall interaction matrix for
            electric field `eField` can be then obtained as
            `fullStarkMatrix` = :obj:`mat1` + :obj:`mat2` *`eField`

            Args:
                n (int): principal quantum number of the state
                l (int): angular orbital momentum of the state
                j (flaot): total angular momentum of the state
                mj (float): projection of total angular momentum of the state
                nMin (int): *minimal* principal quantum number of the states to
                    be included in the basis for calculation
                nMax (int): *maximal* principal quantum number of the states to
                    be included in the basis for calculation
                maxL (int): *maximal* value of orbital angular momentum for the
                    states to be included in the basis for calculation
                Bz (float): optional, magnetic field directed along z-axis in
                    units of Tesla. Calculation will be correct only for weak
                    magnetic fields, where paramagnetic term is much stronger
                    then diamagnetic term. Diamagnetic term is neglected.
                progressOutput (:obj:`bool`, optional): if True prints the
                    progress of calculation; Set to false by default.
                debugOutput (:obj:`bool`, optional): if True prints additional
                    information usefull for debuging. Set to false by default.
                s (float): optional. Total spin angular momentum for the state.
                    Default value of 0.5 is correct for Alkaline Atoms, but
                    value **has to** be specified explicitly for divalent atoms
                    (e.g. `s=0` or `s=1` for singlet and triplet states,
                    that have total spin angular momenutum equal to 0 or 1
                    respectively).
        """
        global wignerPrecal
        wignerPrecal = True
        self.eFieldCouplingSaved = _EFieldCoupling()

        states = []

        # save calculation details START
        self.n = n
        self.l = l
        self.j = j
        self.mj = mj
        self.nMin = nMin
        self.nMax = nMax
        self.maxL = maxL
        self.Bz = Bz
        self.s = s
        # save calculation details END

        for tn in xrange(nMin, nMax):

            for tl in xrange(min(maxL + 1, tn)):
                for tj in np.linspace(tl - s, tl + s, round(2 * s + 1)):
                    if (abs(mj) - 0.1 <= tj) and (
                        tn >= self.atom.groundStateN
                        or [tn, tl, tj] in self.atom.extraLevels
                            ):
                        states.append([tn, tl, tj, mj])

        dimension = len(states)
        if progressOutput:
            print("Found ", dimension, " states.")
            if debugOutput:
                print(states)

        indexOfCoupledState = 0
        index = 0
        for st in states:
            if (st[0] == n) and (abs(st[1] - l) < 0.1) and (abs(st[2] - j) < 0.1) and\
                    (abs(st[3] - mj) < 0.1):
                indexOfCoupledState = index
            index += 1
        if debugOutput:
            print("Index of initial state")
            print(indexOfCoupledState)
            print("Initial state = ")
            print(states[indexOfCoupledState])

        self.mat1 = np.zeros((dimension, dimension), dtype=np.double)
        self.mat2 = np.zeros((dimension, dimension), dtype=np.double)

        self.basisStates = states
        self.indexOfCoupledState = indexOfCoupledState

        if progressOutput:
            print("Generating matrix...")
        progress = 0.

        for ii in xrange(dimension):
            if progressOutput:
                progress += ((dimension - ii) * 2 - 1)
                sys.stdout.write("\r%d%%" %
                                 (float(progress) / float(dimension**2) * 100))
                sys.stdout.flush()

            # add diagonal element
            self.mat1[ii][ii] = self.atom.getEnergy(states[ii][0],
                                                    states[ii][1],
                                                    states[ii][2],
                                                    s=self.s)\
                * C_e / C_h * 1e-9 \
                + self.atom.getZeemanEnergyShift(
                states[ii][1],
                states[ii][2],
                states[ii][3],
                self.Bz,
                s=self.s) / C_h * 1.0e-9
            # add off-diagonal element

            for jj in xrange(ii + 1, dimension):
                coupling = self._eFieldCouplingDivE(states[ii][0], states[ii][1],
                                                    states[ii][2], mj,
                                                    states[jj][0],
                                                    states[jj][1],
                                                    states[jj][2], mj,
                                                    s=self.s) *\
                    1.e-9 / C_h
                self.mat2[jj][ii] = coupling
                self.mat2[ii][jj] = coupling

        if progressOutput:
            print("\n")
        if debugOutput:
            print(self.mat1 + self.mat2)
            print(self.mat2[0])

        self.atom.updateDipoleMatrixElementsFile()
        self.eFieldCouplingSaved._closeDatabase()
        self.eFieldCouplingSaved = False
        return 0

    def diagonalise(self, eFieldList, drivingFromState=[0, 0, 0, 0, 0],
                    progressOutput=False, debugOutput=False):
        """
            Finds atom eigenstates in a given electric field

            Eigenstates are calculated for a list of given electric fields. To
            extract polarizability of the originaly stated state see
            :obj:`getPolarizability` method. Results are saved in
            :obj:`eFieldList`, :obj:`y` and :obj:`highlight`.

            Args:
                eFieldList (array): array of electric field strength (in V/m)
                    for which we want to know energy eigenstates

                progressOutput (:obj:`bool`, optional): if True prints the
                    progress of calculation; Set to false by default.
                debugOutput (:obj:`bool`, optional): if True prints additional
                    information usefull for debuging. Set to false by default.
        """

        # if we are driving from some state
        # ========= FIND LASER COUPLINGS (START) =======

        coupling = []
        dimension = len(self.basisStates)
        self.maxCoupling = 0.
        self.drivingFromState = drivingFromState
        if (self.drivingFromState[0] != 0):
            if progressOutput:
                print("Finding driving field coupling...")
            # get first what was the state we are calculating coupling with
            state1 = drivingFromState
            n1 = int(round(state1[0]))
            l1 = int(round(state1[1]))
            j1 = state1[2]
            m1 = state1[3]
            q = state1[4]

            for i in xrange(dimension):
                thisCoupling = 0.
                if progressOutput:
                    sys.stdout.write("\r%d%%" %
                                     (i / float(dimension - 1) * 100.))
                    sys.stdout.flush()
                if (int(abs(self.basisStates[i][1] - l1)) == 1)and\
                    (int(abs(self.basisStates[i][2] - j1)) <= 1) and\
                        (int(abs(self.basisStates[i][3] - m1 - q)) == 0):
                    state2 = self.basisStates[i]
                    n2 = int(state2[0])
                    l2 = int(state2[1])
                    j2 = state2[2]
                    m2 = state2[3]
                    if debugOutput:
                        print(n1, " ", l1, " ", j1, " ", m1, " < - ", q, " - >", n2, " ",
                              l2, " ", j2, " ", m2, "\n")
                    dme = self.atom.getDipoleMatrixElement(n1, l1, j1, m1,
                                                           n2, l2, j2, m2,
                                                           q,
                                                           s=self.s)
                    thisCoupling += dme
                thisCoupling = abs(thisCoupling)**2
                if thisCoupling > self.maxCoupling:
                    self.maxCoupling = thisCoupling
                if (thisCoupling > 0.00000001) and debugOutput:
                    print("coupling = ", thisCoupling)
                coupling.append(thisCoupling)

            if progressOutput:
                print("\n")

            if self.maxCoupling < 0.00000001:
                raise Exception("State that you specified in drivingFromState, for a " +
                                "given laser polarization, is uncoupled from the specified Stark " +
                                "manifold. If you just want to see the specified Stark manifold " +
                                "remove driveFromState optional argument from call of function " +
                                "diagonalise. Or specify state and driving that is coupled " +
                                "to a given manifold to see coupling strengths.")

        # ========= FIND LASER COUPLINGS (END) =======

        indexOfCoupledState = self.indexOfCoupledState
        self.eFieldList = eFieldList

        self.y = []
        self.highlight = []
        self.composition = []

        if progressOutput:
            print("Finding eigenvectors...")
        progress = 0.
        for eField in eFieldList:
            if progressOutput:
                progress += 1.
                sys.stdout.write("\r%d%%" %
                                 (float(progress) / float(len(eFieldList)) * 100))
                sys.stdout.flush()

            m = self.mat1 + self.mat2 * eField

            ev, egvector = eigh(m)

            self.y.append(ev)
            if (drivingFromState[0] < 0.1):
                sh = []
                comp = []
                for i in xrange(len(ev)):
                    sh.append(abs(egvector[indexOfCoupledState, i])**2)
                    comp.append(self._stateComposition2(egvector[:, i], upTo = 5,totalContribCut=0.99))
                self.highlight.append(sh)
                self.composition.append(comp)
            else:
                sh = []
                comp = []
                for i in xrange(len(ev)):
                    sumCoupledStates = 0.
                    for j in xrange(dimension):
                        sumCoupledStates += abs(coupling[j] / self.maxCoupling) *\
                            abs(egvector[j, i]**2)
                    comp.append(self._stateComposition2(egvector[:, i], upTo = 5,totalContribCut=0.99))
                    sh.append(sumCoupledStates)
                self.highlight.append(sh)
                self.composition.append(comp)

        if progressOutput:
            print("\n")
        return

    def exportData(self, fileBase, exportFormat="csv"):
        """
            Exports StarkMap calculation data.

            Only supported format (selected by default) is .csv in a
            human-readable form with a header that saves details of calculation.
            Function saves three files: 1) `filebase` _eField.csv;
            2) `filebase` _energyLevels
            3) `filebase` _highlight

            For more details on the format, see header of the saved files.

            Args:
                filebase (string): filebase for the names of the saved files
                    without format extension. Add as a prefix a directory path
                    if necessary (e.g. saving outside the current working directory)
                exportFormat (string): optional. Format of the exported file. Currently
                    only .csv is supported but this can be extended in the future.
        """

        fmt = 'on %Y-%m-%d @ %H:%M:%S'
        ts = datetime.datetime.now().strftime(fmt)

        commonHeader = "Export from Alkali Rydberg Calculator (ARC) %s.\n" % ts
        commonHeader += ("\n *** Stark Map for %s %s m_j = %d/2. ***\n\n" % (self.atom.elementName,
                                                                             printStateString(self.n, self.l, self.j), int(round(2. * self.mj))))
        commonHeader += (" - Included states - principal quantum number (n) range [%d-%d].\n" %
                         (self.nMin, self.nMax))
        commonHeader += (" - Included states with orbital momentum (l) in range [%d,%d] (i.e. %s-%s).\n" %
                         (0, self.maxL, printStateLetter(0), printStateLetter(self.maxL)))
        commonHeader += (" - Calculated in manifold where total spin angular momentum is s = %.1d\n" %
                         (self.s))
        if self.drivingFromState[0] < 0.1:
            commonHeader += " - State highlighting based on the relative contribution \n" +\
                "   of the original state in the eigenstates obtained by diagonalization."
        else:
            commonHeader += (" - State highlighting based on the relative driving strength \n" +
                             "   to a given energy eigenstate (energy level) from state\n" +
                             "   %s m_j =%d/2 with polarization q=%d.\n" %
                             (printStateString(*self.drivingFromState[0:3]),
                              int(round(2. * self.drivingFromState[3])),
                                 self.drivingFromState[4]))

        if exportFormat == "csv":
            print("Exporting StarkMap calculation results as .csv ...")

            commonHeader += " - Export consists of three (3) files:\n"
            commonHeader += ("       1) %s,\n" %
                             (fileBase + "_eField." + exportFormat))
            commonHeader += ("       2) %s,\n" %
                             (fileBase + "_energyLevels." + exportFormat))
            commonHeader += ("       3) %s.\n\n" %
                             (fileBase + "_highlight." + exportFormat))

            filename = fileBase + "_eField." + exportFormat
            np.savetxt(filename,
                       self.eFieldList, fmt='%.18e', delimiter=', ',
                       newline='\n',
                       header=(commonHeader + " - - - eField (V/m) - - -"),
                       comments='# ')
            print("   Electric field values (V/m) saved in %s" % filename)

            filename = fileBase + "_energyLevels." + exportFormat
            headerDetails = " NOTE : Each row corresponds to eigenstates for a single specified electric field"
            np.savetxt(filename,
                       self.y, fmt='%.18e', delimiter=', ',
                       newline='\n',
                       header=(commonHeader +
                               ' - - - Energy (GHz) - - -\n' + headerDetails),
                       comments='# ')
            print(
                "   Lists of energies (in GHz relative to ionisation) saved in %s" % filename)

            filename = fileBase + "_highlight." + exportFormat
            np.savetxt(filename,
                       self.highlight, fmt='%.18e', delimiter=', ',
                       newline='\n',
                       header=(
                           commonHeader + ' - - - Highlight value (rel.units) - - -\n' + headerDetails),
                       comments='# ')
            print("   Highlight values saved in %s" % filename)

            print("... data export finished!")
        else:
            raise ValueError("Unsupported export format (.%s)." % format)

    def plotLevelDiagram(self, units=1, highlighState=True, progressOutput=False,
                         debugOutput=False, highlightColour='red',
                         addToExistingPlot=False):
        """
            Makes a plot of a stark map of energy levels

            To save this plot, see :obj:`savePlot`. To print this plot see
            :obj:`showPlot`. Pointers (handles) towards matplotlib figure
            and axis used are saved in :obj:`fig` and :obj:`ax` variables
            respectively.

            Args:
                units (:obj:`int`,optional): possible values {1,2} ; if the
                    value is 1 (default) Stark diagram will be plotted in
                    energy units cm :math:`{}^{-1}`; if value is 2, Stark
                    diagram will be plotted as energy :math:`/h` in units of GHz
                highlightState (:obj:`bool`, optional): False by default. If
                    True, scatter plot colour map will map in red amount of
                    original state for the given eigenState
                progressOutput (:obj:`bool`, optional): if True prints the
                    progress of calculation; Set to False by default.
                debugOutput (:obj:`bool`, optional): if True prints additional
                    information usefull for debuging. Set to False by default.
                addToExistingPlot (:obj:`bool`, optional): if True adds points to
                    existing old plot. Note that then interactive plotting
                    doesn't work. False by default.
        """
        rvb = LinearSegmentedColormap.from_list('mymap',
                                                ['0.9', highlightColour, 'black'])

        self.units = units
        self.addToExistingPlot = addToExistingPlot

        if progressOutput:
            print("plotting...")

        originalState = self.basisStates[self.indexOfCoupledState]
        n = originalState[0]
        l = originalState[1]
        j = originalState[2]

        existingPlot = False
        if (self.fig == 0 or not addToExistingPlot):
            if (self.fig != 0):
                plt.close()
            self.fig, self.ax = plt.subplots(1, 1, figsize=(11., 5))
        else:
            existingPlot = True

        eFieldList = []
        y = []
        yState = []

        for br in xrange(len(self.y)):

            for i in xrange(len(self.y[br])):
                eFieldList.append(self.eFieldList[br])
                y.append(self.y[br][i])
                yState.append(self.highlight[br][i])

        yState = np.array(yState)
        sortOrder = yState.argsort(kind='heapsort')
        eFieldList = np.array(eFieldList)
        y = np.array(y)

        eFieldList = eFieldList[sortOrder]
        y = y[sortOrder]
        yState = yState[sortOrder]

        if (units == 1):
            # in cm^-1

            if not highlighState:
                self.ax.scatter(eFieldList / 100., y * 0.03336,
                                s=1, color="k", picker=5)
            else:
                cm = rvb
                cNorm = matplotlib.colors.Normalize(vmin=0., vmax=1.)
                self.ax.scatter(eFieldList / 100, y * 0.03336,
                                c=yState, s=5, norm=cNorm, cmap=cm, lw=0, picker=5)
                if not existingPlot:
                    cax = self.fig.add_axes([0.91, 0.1, 0.02, 0.8])
                    cb = matplotlib.colorbar.ColorbarBase(
                        cax, cmap=cm, norm=cNorm)
                    if (self.drivingFromState[0] < 0.1):
                        cb.set_label(r"$|\langle %s | \mu \rangle |^2$" %
                                     printStateStringLatex(n, l, j,s=self.s))
                    else:
                        cb.set_label(r"$( \Omega_\mu | \Omega )^2$")

        else:
            # in GHz

            if not highlighState:
                self.ax.scatter(eFieldList / 100., y,
                                s=1, color="k", picker=5)  # in GHz
            else:
                cm = rvb
                cNorm = matplotlib.colors.Normalize(vmin=0., vmax=1.)
                self.ax.scatter(eFieldList / 100., y, c=yState,
                                s=5, norm=cNorm, cmap=cm, lw=0, picker=5)
                if not existingPlot:
                    cax = self.fig.add_axes([0.91, 0.1, 0.02, 0.8])
                    cb = matplotlib.colorbar.ColorbarBase(cax,
                                                          cmap=cm, norm=cNorm)
                    if (self.drivingFromState[0] < 0.1):
                        cb.set_label(r"$|\langle %s | \mu \rangle |^2$" %
                                     printStateStringLatex(n, l, j, s=self.s))
                    else:
                        cb.set_label(r"$(\Omega_\mu / \Omega )^2$")

        self.ax.set_xlabel("Electric field (V/cm)")

        if (units == 1):
            # in cm^{-1}
            uppery = self.atom.getEnergy(
                n, l, j, s=self.s) * C_e / C_h * 1e-9 * 0.03336 + 10
            lowery = self.atom.getEnergy(
                n, l, j, s=self.s) * C_e / C_h * 1e-9 * 0.03336 - 10
            self.ax.set_ylabel("State energy, $E/(h c)$ (cm$^{-1}$)")
        else:
            # in GHz
            uppery = self.atom.getEnergy(n, l, j, s=self.s) * C_e / C_h * 1e-9 + 5
            lowery = self.atom.getEnergy(n, l, j, s=self.s) * C_e / C_h * 1e-9 - 5
            self.ax.set_ylabel(r"State energy, $E/h$ (GHz)")

        self.ax.set_ylim(lowery, uppery)
        ##
        self.ax.set_xlim(min(eFieldList) / 100., max(eFieldList) / 100.)
        return 0

    def savePlot(self, filename="StarkMap.pdf"):
        """
            Saves plot made by :obj:`plotLevelDiagram`

            Args:
                filename (:obj:`str`, optional): file location where the plot
                    should be saved
        """
        if (self.fig != 0):
            self.fig.savefig(filename, bbox_inches='tight')
        else:
            print("Error while saving a plot: nothing is plotted yet")
        return 0

    def showPlot(self, interactive=True):
        """
            Shows plot made by :obj:`plotLevelDiagram`
        """
        if (self.fig != 0):
            if interactive:
                if self.addToExistingPlot:
                    print("NOTE: Interactive plotting doesn't work with"
                          " addToExistingPlot option set to True"
                          "\nPlease turn off this option in plotLevelDiagram.\n")
                else:
                    self.ax.set_title(
                        "Click on state to see state composition")
                    self.clickedPoint = 0
                    self.fig.canvas.draw()
                    self.fig.canvas.mpl_connect('pick_event', self._onPick)
            plt.show()
        else:
            print("Error while showing a plot: nothing is plotted yet")
        return 0

    def _onPick(self, event):
        if isinstance(event.artist, matplotlib.collections.PathCollection):
            if (self.units == 1):
                scaleFactor = 0.03336
            else:
                scaleFactor = 1.0

            x = event.mouseevent.xdata * 100.
            y = event.mouseevent.ydata / scaleFactor

            i = np.searchsorted(self.eFieldList, x)
            if i == len(self.eFieldList):
                i -= 1
            if ((i > 0) and (abs(self.eFieldList[i - 1] - x) < abs(self.eFieldList[i] - x))):
                i -= 1

            j = 0
            for jj in xrange(len(self.y[i])):
                if (abs(self.y[i][jj] - y) < abs(self.y[i][j] - y)):
                    j = jj

            # now choose the most higlighted state in this area
            distance = abs(self.y[i][j] - y) * 1.5
            for jj in xrange(len(self.y[i])):
                if (abs(self.y[i][jj] - y) < distance and
                        (abs(self.highlight[i][jj]) > abs(self.highlight[i][j]))):
                    j = jj

            if (self.clickedPoint != 0):
                self.clickedPoint.remove()

            self.clickedPoint, = self.ax.plot([self.eFieldList[i] / 100.],
                                              [self.y[i][j] * scaleFactor], "bs",
                                              linewidth=0, zorder=3)

            self.ax.set_title(("[%s] = " % self.atom.elementName) +
                              self._stateComposition(self.composition[i][j]) +
                              ("   Colourbar value = %.2f" %
                               self.highlight[i][j]),
                              fontsize=11)

            event.canvas.draw()

    def _stateComposition(self, stateVector, totalContribCut = 0.95):
        # stateVector: first is the state amplitude and second is the state index in self.basisStates
        i = 0
        totalContribution = 0
        value = "$"
        while (i < len(stateVector)) and (totalContribution < totalContribCut):
            if (i != 0 and stateVector[i][0] > 0):
                value += "+"
            value = value + ("%.2f" % stateVector[i][0]) +\
                self._addState(*self.basisStates[stateVector[i][1]])
            totalContribution += abs(stateVector[i][0])**2
            i += 1

        if totalContribution < 0.999:
            value += "+\\ldots"
        return value + "$"

    def _stateComposition2(self, stateVector, upTo=4, totalContribCut = 0.95):
        contribution = np.absolute(stateVector)
        order = np.argsort(contribution, kind='heapsort')
        index = -1
        totalContribution = 0
        mainStates = []  # [state Value, state index]
        while (index > -upTo) and (totalContribution < totalContribCut):
            i = order[index]
            mainStates.append([stateVector[i], i])
            totalContribution += contribution[i]**2
            index -= 1
        return mainStates

    def _addState(self, n1, l1, j1, mj1):
        if abs(self.s - 0.5) < 0.1:
            # we have Alkali Atoms
            return "|%s m_j=%d/2\\rangle" %\
                (printStateStringLatex(n1, l1, j1), int(2 * mj1))
        else:
            # we have singlets or triplets states of divalent atoms
            return "|%s m_j=%d\\rangle" %\
                (printStateStringLatex(n1, l1, j1, s=self.s), int(mj1))

    @staticmethod
    def _isCoupled(n, l, j, n1, l1, j1):
        if (not(n == n1 and l == l1 and j == j1) 
            and not(abs(l1 - l) != 1
                        and( (abs(j - 0.5) < 0.1
                            and abs(j1 - 0.5) < 0.1) # j = 1/2 and j'=1/2 forbidden
                            or
                            (abs(j) < 0.1
                            and abs(j1 - 1) < 0.1)  # j = 0 and j'=1 forbidden
                            or
                            (abs(j-1) < 0.1
                            and abs(j1) < 0.1)  # j = 1 and j'=0 forbidden
                        )
                    )
                and not(abs(j)<0.1 and abs(j1)<0.1)  # j = 0 and j'=0 forbiden
                and not(abs(l)<0.1 and abs(l1)<0.1) # l = 0 and l' = 0 is forbiden
            ):
            # determine coupling
            dl = abs(l - l1)
            dj = abs(j - j1)
            c1 = 0
            if dl == 1 and (dj < 1.1):
                c1 = 1  # dipole coupling
            elif (dl == 0 or dl == 2 or dl == 1)and (dj < 2.1):
                c1 = 2  # quadrupole coupling
            else:
                return False
            return c1
        else:
            return False


    def getPolarizability(self, maxField=1.e10, showPlot=False,
                          debugOutput=False, minStateContribution=0.0):
        r"""
            Returns the polarizability of the state (set during the
            initalization process).

            Fits offset of the energy level of the state to
            :math:`\frac{1}{2}  \alpha_0  E^2`, where
            :math:`E` is the applied static electric field,
            and returns fitted value :math:`\alpha_0`

            Args:
                maxField (:obj:`float`, optional): maximum field (in V/m) to be
                    used for fitting the polarizability. By default, max field
                    is very large, so it will use eigenvalues calculated in the
                    whole range.
                showPlot (:obj:`bool`, optional): shows plot of calculated
                    eigenValues of the given state (dots), and the fit (solid
                    line) for extracting polarizability
                debugOutput (:obj:`bool`, optional): if True prints additional
                    information usefull for debuging. Set to false by default.


            Returns:
                float: scalar polarizability in units of MHz cm :math:`^2` / V \
                :math:`^2`
        """
        if (self.drivingFromState[0] != 0):
            raise Exception("Program can only find Polarizability of the original " +
                            "state if you highlight original state. You can do so by NOT " +
                            "specifying drivingFromState in diagonalise function.")

        eFieldList = self.eFieldList
        yState = self.highlight
        y = self.y

        originalState = self.basisStates[self.indexOfCoupledState]
        n = originalState[0]
        l = originalState[1]
        j = originalState[2]
        energyOfOriginalState = self.atom.getEnergy(
            n, l, j, s=self.s) * C_e / C_h * 1e-9  # in  GHz

        if debugOutput:
            print("finding original state for each electric field value")

        stopFitIndex = 0
        while stopFitIndex < len(eFieldList) - 1 and \
                eFieldList[stopFitIndex] < maxField:
            stopFitIndex += 1

        xOriginalState = []
        yOriginalState = []

        for ii in xrange(stopFitIndex):

            maxPortion = 0.
            yval = 0.
            jj = 0
            for jj in xrange(len(y[ii])):
                if yState[ii][jj] > maxPortion:
                    maxPortion = yState[ii][jj]
                    yval = y[ii][jj]
            # measure state energy relative to the original state
            if (minStateContribution < maxPortion):
                xOriginalState.append(eFieldList[ii])
                yOriginalState.append(yval - energyOfOriginalState)

        xOriginalState = np.array(xOriginalState) / 100.  # converts to V/cm
        yOriginalState = np.array(yOriginalState)   # in GHz

        # in GHz
        uppery = 5.0
        lowery = -5.0

        if debugOutput:
            print("found ", len(xOriginalState))
        if showPlot:
            self.fig, self.ax = plt.subplots(1, 1, figsize=(6.5, 3))
            self.ax.scatter(xOriginalState, yOriginalState, s=2, color="k")

            self.ax.set_xlabel("E field (V/cm)")

            self.ax.set_ylim(lowery, uppery)
            self.ax.set_ylabel(r"Energy/$h$ (GHz)")
            self.ax.set_xlim(xOriginalState[0],
                             xOriginalState[-1])

        def polarizabilityFit(eField, offset, alpha):
            return offset - 0.5 * alpha * eField**2

        try:
            popt, pcov = curve_fit(polarizabilityFit,
                                   xOriginalState,
                                   yOriginalState,
                                   [0, 0])
        except Exception as ex:
            print(ex)
            print("\nERROR: fitting energy levels for extracting polarizability\
                    of the state failed. Please check the range of electric \
                    fields where you are trying to fit polarizability and ensure\
                    that there is only one state with continuous energy change\
                    that has dominant contribution of the initial state.\n\n")
            return 0

        if debugOutput:
            print("Scalar polarizability = ",
                  popt[1] * 1.e3, " MHz cm^2 / V^2 ")

        y_fit = []
        for val in xOriginalState:
            y_fit.append(polarizabilityFit(val, popt[0], popt[1]))
        y_fit = np.array(y_fit)

        if showPlot:
            self.ax.plot(xOriginalState, y_fit, "r--")
            self.ax.legend(("fitted model function", "calculated energy level"),
                           loc=1, fontsize=10)

            self.ax.set_ylim(min(yOriginalState), max(yOriginalState))

            plt.show()

        self.fitX = xOriginalState
        self.fitY = yOriginalState
        self.fittedCurveY = y_fit

        return popt[1] * 1.e3  # returned value is in  MHz cm^2 / V^2


    def getState(self, state, electricField, minN, maxN, maxL,
                 accountForAmplitude=0.95,
                 debugOutput=False):
        """
        Returns basis states and coefficients that make up for a given electric
        field the eigenstate with largest contribution of the original state.

        Args:
            state (array): target basis state in format :math:`[n,\ell,j,m_j]`
                corresponding to the state whose composition we want to track
                as we apply the electric field
            electricField (float): applied DC electric field in units of V/m.
            minN (int): minimal principal quantum number to be taken for calculation
                of the Stark mixing
            maxN (int): maximal principal quantum nunber to be take for calculation
                of the Start mixing
            maxL (int): maximal orbital angular momentum of states that should be
                taken in calculation of the Stark mixing
            accountForAmplitude (float): optinal, relative amplitude of state
                that should be reached with the subset of the eigen states
                returned. The returned eigen states will be sorted in the
                declining relative contribution to the final eigen state, and
                once total accounted amplitude of the state reaches 0.95,
                further output of additional small contribution of the other
                basis states to the final states will be supressed. Default
                value of 0.95 will force output until basis state accounts
                for 95\% of the state amplitude.
            debugOutput (bool): optional, prints additional debug information
                if True. Default False.

        Returns:
            **array of states** in format [[n1, l1, j1, mj1], ...] and
            **array of complex coefficients** in format [c1, c2, ...] corresponding
            the projections of the eigenstate (thas has largest contribution
            of the original state in the given electric field) on the basis
            states,
            and **energy** of the found state in (eV)

        """
        self.defineBasis(state[0], state[1], state[2], state[3],
                         minN, maxN, maxL)

        m = self.mat1 + self.mat2 * electricField
        ev, egvector = eigh(m)

        # find which state in the electric field has strongest contribution
        # of the requested state?
        maxOverlap = 0
        eigenvectorIndex = 0
        for i in range(len(ev)):
            if ( abs(egvector[self.indexOfCoupledState, i])**2 > maxOverlap ):
                maxOverlap = abs( egvector[self.indexOfCoupledState, i] )**2
                eigenvectorIndex = i

        energy = ev[eigenvectorIndex] * 0.03336
        if debugOutput:
            print("Max overlap = %.3f" % maxOverlap)
            print("Eigen energy (state index %d) = %.2f eV" % (eigenvectorIndex,
                                                               energy))

        contributions = egvector[:, eigenvectorIndex]
        sortedContributions = np.argsort(abs(contributions) )

        if debugOutput:
            print("Maximum contributions to this state")
            for i in range(4):
                index = sortedContributions[-i-1]
                print(contributions[index])
                print(self.basisStates[index])
            print("===========\n")

        i = 0
        coef = []
        contributingStates = []
        while (accountForAmplitude > 0 and i < len(self.basisStates)):
            index = sortedContributions[-i-1]
            coef.append(contributions[index])
            accountForAmplitude -= abs(coef[-1])**2
            contributingStates.append(self.basisStates[index])
            i += 1

        return contributingStates, coef, energy

# ================= Level plots, decays, cascades etc =======================

class LevelPlot:
    """
        Single atom level plots and decays (a Grotrian diagram, or term diagram)

        For an example see `Rydberg energy levels example snippet`_.

        .. _`Rydberg energy levels example snippet`:
            ./Rydberg_atoms_a_primer.html#Rydberg-Atom-Energy-Levels

        Args:
            atom (:obj:`AlkaliAtom` or :obj:`DivalentAtom`): ={
                :obj:`arc.alkali_atom_data.Lithium6`,
                :obj:`arc.alkali_atom_data.Lithium7`,
                :obj:`arc.alkali_atom_data.Sodium`,
                :obj:`arc.alkali_atom_data.Potassium39`,
                :obj:`arc.alkali_atom_data.Potassium40`,
                :obj:`arc.alkali_atom_data.Potassium41`,
                :obj:`arc.alkali_atom_data.Rubidium85`,
                :obj:`arc.alkali_atom_data.Rubidium87`,
                :obj:`arc.alkali_atom_data.Caesium`,
                :obj:`arc.divalent_atom_data.Strontium88`,
                :obj:`arc.divalent_atom_data.Calcium40`
                :obj:`arc.divalent_atom_data.Ytterbium174` }
                Alkali atom type whose levels we
                want to examine
    """

    def __init__(self, atomType):
        self.atom = atomType
        self.nFrom = 0
        self.nTo = 0
        self.lFrom = 0
        self.lTo = 0
        self.sList = []

        self.listX = []
        self.listY = []   # list of energies
        self.levelLabel = []

        self.fig = 0
        self.ax = 0
        self.width = 0.2
        self.state1 = [0, 0, 0]
        self.state2 = [0, -1, 0]
        self.transitionMatrix = []
        self.populations = []
        self.transitionMatrixWavelength3 = []

        # characterization of the graph
        self.spectraX = []
        self.spectraY = []
        self.spectraLine = []

    def makeLevels(self, nFrom, nTo, lFrom, lTo, sList=[0.5]):
        """
            Constructs energy level diagram in a given range

            Args:
                nFrom (int): minimal principal quantum number of the
                    states we are interested in
                nTo (int): maximal principal quantum number of the
                    states we are interested in
                lFrom (int): minimal orbital angular momentum
                    of the states we are interested in
                lTo (int): maximal orbital angular momentum
                    of the states we are interested in
                sList (float): optional, spin angular momentum. Default value
                    of [0.5] corresponds to Alkali atoms. For Alkaline Earth it
                    has to be specified. For divalent atoms one can plot either
                    one spin state by setting for example `sList=[0]``,
                    or both spin states `sList=[0,1]``
        """
        # save local copy of the space restrictions
        self.nFrom = nFrom
        self.nTo = nTo
        self.lFrom = lFrom
        self.lTo = lTo
        self.sList = sList

        # find all the levels within this space restrictions
        xPositionOffset = 0
        for s in sList:
            n = max(self.nFrom, self.atom.groundStateN)
            while n <= nTo:
                l = lFrom
                if (l==0 and s==1 and n == self.atom.groundStateN):
                    # for ground state S state, there is only singlet
                    l += 1
                while l <= min(lTo, n - 1):
                    for j in np.linspace(l - s, l + s, round(2 * s + 1)):
                        if j > -0.1:
                            self.listX.append(l + xPositionOffset)
                            self.listY.append(self.atom.getEnergy(n, l, j,
                                                                  s=s))
                            self.levelLabel.append([n, l, j, s])
                    l = l + 1
                n += 1

            # if user requested principal quantum nuber below theself.listX_l.append(l)
            # ground state principal quantum number
            # add those L states that are higher in energy then the ground state
            for state in self.atom.extraLevels:
                if state[1] <= lTo and state[0] >= self.nFrom and \
                        (len(state)==3 or state[3]==s):
                    # last line means: either is Alkali, when we don't need to
                    # check the spin, or it's divalent, when we do need to check
                    # the spin
                    self.listX.append(state[1] + xPositionOffset)
                    self.listY.append(self.atom.getEnergy(
                        state[0], state[1], state[2], s=s))
                    self.levelLabel.append([state[0], state[1], state[2], s])

            xPositionOffset += lTo + 1


    def makeTransitionMatrix(self, environmentTemperature=0.0, printDecays=True):
        self.transitionMatrix = []

        for i in xrange(len(self.levelLabel)):
            state1 = self.levelLabel[i]
            transitionVector = []

            # decay of the stay
            decay = 0.0

            for state2 in self.levelLabel:
                dipoleAllowed = (abs(state1[1] - state2[1]) == 1)and\
                                (abs(state1[2] - state2[2]) <= 1.01)
                if (dipoleAllowed):
                    # decay to this state
                    rate = self.atom.getTransitionRate(state2[0], state2[1], state2[2],
                                                       state1[0], state1[1], state1[2],
                                                       temperature=environmentTemperature)

                    transitionVector.append(rate)

                    # decay from this state
                    rate = self.atom.getTransitionRate(state1[0], state1[1], state1[2],
                                                       state2[0], state2[1], state2[2],
                                                       temperature=environmentTemperature)

                    decay = decay - rate
                else:
                    transitionVector.append(0.0)

            transitionVector[i] = decay
            if printDecays:
                print("Decay time of ")
                printState(state1[0], state1[1], state1[2])
                if decay < -1e-20:
                    print("\t is\t", -1.e9 / decay, " ns")
            self.transitionMatrix.append(transitionVector)

        np.array(self.transitionMatrix)

        self.transitionMatrix = np.transpose(self.transitionMatrix)

    def drawSpectra(self):
        self.fig, self.ax = plt.subplots(1, 1, figsize=(16, 5))

        lineWavelength = []
        lineStrength = []
        lineName = []
        i = 0
        while i < len(self.levelLabel):
            j = 0
            while j < len(self.levelLabel):
                if (i != j):
                    wavelength = self.atom.getTransitionWavelength(
                        self.levelLabel[i][0],
                        self.levelLabel[i][1], self.levelLabel[i][2],
                        self.levelLabel[j][0],
                        self.levelLabel[j][1], self.levelLabel[j][2])

                    intensity = self.atom.getTransitionRate(self.levelLabel[i][0],
                                                            self.levelLabel[i][1], self.levelLabel[i][2],
                                                            self.levelLabel[j][0],
                                                            self.levelLabel[j][1], self.levelLabel[j][2])

                    lineWavelength.append(abs(wavelength) * 1.e9)
                    lineStrength.append(abs(intensity))
                    lineName.append(printStateString(self.levelLabel[i][0],
                                                     self.levelLabel[i][1],
                                                     self.levelLabel[i][2]) +
                                    " -> " +
                                    printStateString(self.levelLabel[j][0],
                                                     self.levelLabel[j][1],
                                                     self.levelLabel[j][2]))

                j = j + 1
            i = i + 1

        self.spectraX = np.copy(lineWavelength)
        self.spectraY = np.copy(lineStrength)
        self.spectraLine = np.copy(lineName)

    def drawSpectraConvoluted(self, lowerWavelength, higherWavelength, points, gamma):
        wavelengths = np.linspace(lowerWavelength, higherWavelength, points)
        spectra = np.zeros(points)
        i = 0
        while i < len(wavelengths):
            value = 0
            j = 0
            while j < len(self.spectraX):
                value = value + self.spectraY[j] * gamma /\
                    ((self.spectraX[j] - wavelengths[i])**2 + gamma**2)
                j = j + 1
            spectra[i] = value
            i = i + 1
        self.ax.plot(wavelengths, spectra, "g-")

    def showSpectra(self, saveInFile="", showTransitionPoints=True):
        if showTransitionPoints:
            self.ax.plot(self.spectraX, self.spectraY, "ro", picker=5)
        self.ax.set_xlabel("Wavelength (nm)")
        self.ax.set_ylabel("Intensity (arb.un)")
        self.fig.subplots_adjust(right=0.95, left=0.1)
        # self.ax.set_xlim(300,600)
        self.fig.canvas.mpl_connect('pick_event', self.onpick3)
        if (saveInFile != ""):
            self.fig.savefig(saveInFile)
        plt.show()

    def drawLevels(self):
        """
            Draws a level diagram plot
        """
        self.fig, self.ax = plt.subplots(1, 1, figsize=(9.0, 11.5))

        i = 0
        while i < len(self.listX):
            self.ax.plot([self.listX[i] - self.width,
                                 self.listX[i] + self.width],
                         [self.listY[i], self.listY[i]], "b-", picker=True)
            if (i < len(self.populations) and (self.populations[i] > 1e-3)):
                self.ax.plot([self.listX[i]], [self.listY[i]],
                             "ro", alpha=self.populations[i])

            i = i + 1

    def showPlot(self):
        """
            Shows a level diagram plot
        """
        self.listX = np.array(self.listX)
        self.ax.set_ylabel("Energy (eV)")
        self.ax.set_xlim(-0.5 + np.min(self.listX), np.max(self.listX) + 0.5)

        # X AXIS
        majorLocator = MultipleLocator(1)

        self.ax.xaxis.set_major_locator(majorLocator)
        tickNames = []
        for s in self.sList:
            sNumber  = round(2 * s + 1)
            for l in xrange(self.lFrom, self.lTo + 1):
                tickNames.append("$^%d %s$" % (sNumber, printStateLetter(l) ) )
        tickNum = len(tickNames)

        self.fig.canvas.draw()
        self.ax.set_xticks(np.arange(tickNum))
        self.ax.set_xticklabels(tickNames)
        self.ax.set_xlim(-0.5 + np.min(self.listX), np.max(self.listX) + 0.5)
        self.fig.canvas.mpl_connect('pick_event', self.onpick2)
        self.state1[0] = -1  # initialise for picking
        plt.show()

    def findState(self, x, y):
        distance = 100000000.0
        state = [0, 0, 0]
        i = 0
        while i < len(self.listX):
            dx = self.listX[i] - x
            dy = self.listY[i] - y
            dist = sqrt(dx * dx + dy * dy)
            if (dist < distance):
                distance = dist
                state = self.levelLabel[i]
            i = i + 1
        return state

    def findStateNo(self, state):
        # returns no of the given state in the basis
        i = 0
        while i < len(self.levelLabel):
            if (self.levelLabel[i][0] == state[0])and\
                (self.levelLabel[i][1] == state[1])and\
                    (abs(self.levelLabel[i][2] - state[2]) < 0.01):
                return i
            i = i + 1

        print("Error: requested state ")
        print(state)
        print("could not be found!")
        return -1

    def findLine(self, x, y):
        distance = 1.e19
        line = ""
        i = 0
        while i < len(self.spectraLine):
            dx = self.spectraX[i] - x
            dy = self.spectraY[i] - y
            dist = sqrt(dx * dx + dy * dy)
            if (dist < distance):
                distance = dist
                line = self.spectraLine[i]
            i = i + 1
        return line

    def onpick2(self, event):
        if isinstance(event.artist, matplotlib.lines.Line2D):
            thisline = event.artist
            xdata = thisline.get_xdata()
            ydata = thisline.get_ydata()

            state = self.findState((xdata[0] + xdata[0]) / 2., ydata[0])
            if (self.state1[0] == -1 or (state[1] == self.state1[1])):
                self.state1 = state
                self.ax.set_title(r"$%s \rightarrow$ " % (printStateStringLatex(
                    state[0], state[1], state[2], s=state[3])) )
                self.state2 = [-1, -1, -1]
            else:
                title = ""
                if (state[1] != self.state1[1]) and (state[1] != self.state2[1]):
                    title = (r"$ %s \rightarrow %s $ " %
                             (printStateStringLatex(self.state1[0],
                                             self.state1[1],
                                             self.state1[2], s=self.state1[3]),

                                printStateStringLatex(state[0], state[1], state[2],
                                                      s=state[3])))
                    title = title + (" %.2f nm (%.3f GHz)" %
                                     (self.atom.getTransitionWavelength(self.state1[0],
                                                                        self.state1[1],
                                                                        self.state1[2],
                                                                        state[0], state[1],
                                                                        state[2],
                                                                        s=self.state1[3],
                                                                        s2=state[3]) * 1e9,
                                      self.atom.getTransitionFrequency(self.state1[0],
                                                                       self.state1[1],
                                                                       self.state1[2],
                                                                       state[0],
                                                                       state[1],
                                                                       state[2],
                                                                       s=self.state1[3],
                                                                       s2=state[3]) * 1e-9))
                    self.ax.set_title(title)
                    self.state1 = [0, 0, 0]

                self.state2[1] = state[1]
            event.canvas.draw()

    def onpick3(self, event):
        if isinstance(event.artist, Line2D):
            thisline = event.artist
            xdata = thisline.get_xdata()
            ydata = thisline.get_ydata()
            ind = event.ind
            print(ind[0])

            line = self.findLine(xdata[ind][0], ydata[ind][0])
            self.ax.set_title(line)
            event.canvas.draw()


class AtomSurfaceVdW:
    r"""
        Calculates atom-surface Van der Waals interaction.

        Energy of atom state :math:`|i\rangle` at distance :math:`z`
        from the surface of material is offseted in energy by
        :math:`V_{\rm VdW}` at small distances
        :math:`z\ll\rm{min}(\lambda_{i,j})` ,
        where :math:`\lambda_{i,j}` are the wavelengths from atom state
        :math:`|i \rangle` to all strongly-coupled states :math:`j` ,
        due to (unretarded) atom-surface interaction, also called
        Van der Waals interaction.
        The interaction potential can be expressed as

        :math:`V_{\rm VdW} = - \frac{C_3}{z^3}`

        This class calculates :math:`C_3` for individual states
        :math:`|i\rangle`.

        See example `atom-surface calculation snippet`_.

        .. _`atom-surface calculation snippet`:
            ./ARC_3_0_introduction.html#Atom-surface-van-der-Waals-interactions-(C3-calculation)

        Args:
            atom (:obj:`AlkaliAtom` or :obj:`DivalentAtom`): specified
                Alkali or Alkaline Earth atom whose interaction with surface
                we want to explore
            material (from :obj:`arc.materials`): specified surface material

        Note:
            To find frequecy shift of a transition
            :math:`|\rm a \rangle\rightarrow |\rm b \rangle`,
            one needs to calculate difference in
            :math:`C_3` coefficients obtained for the two states
            :math:`|\rm a\rangle` and :math:`|\rm b\rangle` respectively.
            See example TODO (TO-DO)

    """

    def __init__(self, atom, surfaceMaterial=None):
        self.atom = atom
        if surfaceMaterial is None:
            print("NOTE: No surface material specified. "
                  "Assuming perfect mirror.")
        self.surfaceMaterial = surfaceMaterial

    def getC3contribution(self,
                          n1, l1, j1,
                          n2, l2, j2,
                          s=0.5):
        r"""
        Contribution to :math:`C_3` of :math:`|n_1, \ell_1, j_1\rangle` state
        due to dipole coupling to :math:`|n_2, \ell_2, j_2\rangle` state.

        Calculates
        :math:`\frac{1}{4\pi\varepsilon_0}\
        \frac{ n(\omega_{\rm ab})^2 - 1}{ n(\omega_{\rm ab})^2 + 1}\
        \frac{
        \left| \langle a| D_x | b \rangle \right|^2 \
        + \left| \langle a | D_y  | b \rangle \right|^2 + \
        2 \cdot \left|\langle a |D_z| b \rangle \right|^2}{16}`

        where :math:`|{\rm a}\rangle \equiv |n_1, \ell_1, j_1\rangle` ,
        :math:`|{\rm b}\rangle \equiv |n_2, \ell_2, j_2\rangle`,
        :math:`\mathbf{D} \equiv e \cdot \mathbf{r} \
        \equiv \hat{x} D_x + \hat{y} D_y\
        + \hat{z} D_z` is atomic dipole operator and :math:`n(\omega_{\rm ab})`
        is refractive index of the considered surface at transition frequency
        :math:`\omega_{\rm ab}` .

        Args:
            n1 (int): principal quantum number of state 1
            l1 (int): orbital angular momentum of state 1
            j1 (float): total angular momentum of state 1
            n2 (int): principal quantum number od state 2
            l2 (int): orbital angular momentum of state 2
            j2 (float): total angular momentum of state 2
            s (float): optional, spin angular momentum of states. Default value
                of 0.5 is correct for AlkaliAtoms. For DivalentAtom it
                has to be explicitly stated

        Returns:
            float, float, float:
                contribution to VdW coefficient :math:`C_3` ,\
                estimated error :math:`\delta C_3` \
                (in units of :math:`{\rm J}\cdot{\rm m}^3`), and refractive \
                index :math:`n` of the surface material for the given \
                transition.

        Warning:
            This is just contribution of one transition to the level shift
            of a particular state. To calculate total level shift, check
            :obj:`AtomSurfaceVdW.getStateC3`
        """

        result = 0.
        error = 0.

        hasLiteratureValue, dme, info = self.atom.getLiteratureDME(
            n1, l1, j1,
            n2, l2, j2,
            s=0.5)
        if hasLiteratureValue:
            dme_reduced_J = self.atom.getReducedMatrixElementJ(
                n1, l1, j1,
                n2, l2, j2,
                s=0.5)
            relativeError = abs(info[1]/dme_reduced_J)
        else:
            relativeError = 0.05  # 5 percent for calculated values (note: estimate only!)

        # sum over mj1
        for mj1 in np.linspace(-j1, j1, int(round(2 * j1 + 1))):

            # calculate sum_mj2 |<j1,mj1|Dx|j2,mj2>|^2 + |<j1,mj1|Dy|j2,mj2>|^2 + 2* |<j1,mj1|Dz|j2,mj2>|^2
            # which is equal to (check!)  |<j1,mj1|D+|j2,mj2>|^2 + |<j1,mj1|D-|j2,mj2>|^2 + 2* |<j1,mj1|Dz|j2,mj2>|^2
            for mj2 in np.linspace(-j2, j2, int(round(2 * j2 + 1, 0))):
                for q in [-1, +1]:
                    result += abs(
                        self.atom.getDipoleMatrixElement(n1, l1, j1, mj1,
                                                         n2, l2, j2, mj2,
                                                         q, s=s)
                        * C_e * physical_constants["Bohr radius"][0]
                        )**2
                    error += (
                        2 * abs(self.atom.getDipoleMatrixElement(n1, l1, j1, mj1,
                                                                 n2, l2, j2, mj2,
                                                                 q, s=s)
                                * C_e * physical_constants["Bohr radius"][0]
                               )**2
                        * relativeError
                        )
                # for q = 0
                q = 0
                result += 2 * abs(
                    self.atom.getDipoleMatrixElement(n1, l1, j1, mj1,
                                                     n2, l2, j2, mj2,
                                                     q)
                    * C_e * physical_constants["Bohr radius"][0]
                    )**2
                error += (
                    2 * abs(self.atom.getDipoleMatrixElement(n1, l1, j1, mj1,
                                                             n2, l2, j2, mj2,
                                                             q)
                            * C_e * physical_constants["Bohr radius"][0]
                            )**2
                    * relativeError)

        materialFactor = 1.
        n = 10000
        # effectively infinite refractive index would correspond to perfect
        # reflector (perfect mirror)

        if self.surfaceMaterial is not None:
            wavelength = np.abs(self.atom.getTransitionWavelength(n1, l1, j1,
                                                                  n2, l2, j2,
                                                                  s=s, s2=s)
                                ) * 1e6  # in mum
            n = self.surfaceMaterial.getN(vacuumWavelength=wavelength)
            materialFactor = (n**2 - 1.) / (n**2 + 1.)

        # include factor of 16

        result = result / (2 * j1 + 1) / 16
        error = error / (2 * j1 + 1) / 16

        C3 = materialFactor * 1 / (4.0 * pi * epsilon_0) * result
        error = materialFactor * 1 / (4.0 * pi * epsilon_0) * error

        return C3, error, n  # C3 and error in units of J m^3

    def getStateC3(self, n, l, j, coupledStatesList, s=0.5, debugOutput=False):
        r"""
        Van der Waals atom-surface interaction coefficient for
        a given state (:math:`C_3` in units of
        :math:`\mathrm{J}\cdot\mathrm{m}^3` )

        Args:
            n (int): principal quantum number of the state
            l (int): orbital angular momentum of the state
            j (int): total angular momentum of state
            coupledStatesList (array): array of states that are strongly
                dipole-coupled to the initial state, whose contribution
                to :math:`C_3` will be take into account. Format
                `[[n1,l1,j1],...]`
            s (float, optional): total spin angular momentum for the considered
                state. Default value of 0.5 is correct for `AlkaliAtoms`, but
                it has to be explicitly specifiied for `DivalentAtom`.
            debugOutput (bool, optional): prints additional output information,
                False by default.

        Returns:
            float, float:
                :math:`C_3` (in units of :math:`{\rm J}\cdot {\rm m}^3` ),
                estimated error :math:`\delta C_3`
        """

        if debugOutput:
            print("%s ->\tC3 contr. (kHz mum^3) \tlambda (mum)\tn"
                  % (printStateString(n, l, j, s=s))
                  )

        totalShift = 0
        sumSqError = 0

        for state in coupledStatesList:
            c3, err, refIndex = self.getC3contribution(
                n, l, j,
                state[0], state[1], state[2],
                s=s)
            if debugOutput:
                print(
                    "-> %s\t%.3f +- %.3f    \t%.3f\t\t%.3f\n" %
                    (printStateString(state[0], state[1], state[2], s=s),
                     c3/C_h*(1e6)**3*1e-3,
                     err/C_h*(1e6)**3*1e-3,
                     self.atom.getTransitionWavelength(
                         n, l, j,
                         state[0], state[1], state[2], s=s, s2=s) * 1e6,
                     refIndex)
                    )
            totalShift += c3
            sumSqError += err**2
        error = np.sqrt(sumSqError)
        if debugOutput:
            print("= = = = = = \tTotal shift of %s\t= %.3f+-%.4f kHz mum^3\n" %
                  (printStateString(n, l, j, s=s),
                   totalShift/C_h * (1e6)**3 * 1e-3,
                   error/C_h * (1e6)**3 * 1e-3))

        return totalShift, error  # in J m^3


class OpticalLattice1D:
    r"""
        Atom properties in optical lattices in 1D.

        See example `optical lattice calculations snippet`_.

        .. _`optical lattice calculations snippet`:
            ./ARC_3_0_introduction.html#Optical-lattice-calculations-(Bloch-bands,-Wannier-states...)

        Args:
            atom: one of AlkaliAtom or DivalentAtom
            trapWavenegth (float): wavelength of trapping laser light
                (in units of m)
    """


    energy = []
    """
        energy of states obtained by
        :obj:`OpticalLattice1D.diagonalise` method
        in format `[[energies for quasimomentum1 ],  [energies for quasimomentum2 ], ...]`
    """

    quasimomentum = []
    """
        list of quzimomentum for which the energies of states was calculated
        by :obj:`OpticalLattice1D.diagonalise` method
        in format `[quasimomentum1, quasimomentum2, ...]`
    """

    savedBlochBand = []
    """
        list of saved eigen energy state compositions for each of the Calculated
        quasimomentums for the selected index of the Bloch band
        in :obj:`OpticalLattice1D.diagonalise` method
        in format `[[eigen state decomposition for quasimomentum 1],
        [eigen state decomposition for quasimomentum 2], ...]`
    """

    trapPotentialDepth = 0
    """
        save slattice trap potential depth for which calculation
        :obj:`OpticalLattice1D.diagonalise` was done
    """

    def __init__(self, atom, trapWavenegth):
        self.atom = atom
        self.trapWavenegth = trapWavenegth

    def getRecoilEnergy(self):
        """
        Recoil energy for atoms in given optical lattice

        Returns:
            float: recoil energy in units of J
        """
        latticeConstant = self.trapWavenegth / 2
        Er = C_h**2 / (8 * self.atom.mass * latticeConstant**2)
        return Er

    def getTrappingFrequency(self, trapPotentialDepth):
        """
        Atom's trapping frequecy for given trapth depth

        Args:
            trapPotentialDepth (float): lattice depth (in units of J)

        Returns:
            float: trapping frequency (in Hz)
        """
        Er = self.getRecoilEnergy()
        return 2. * Er / hbar * np.sqrt(trapPotentialDepth / Er)

    def _BlochFunction(self, x, stateVector, q, k=1.):
        r"""
        Bloch wavefunctions

        Args:
            x (x): position (in units \2 pi/k, for default value of laser
                wavevector unit k=1, one full wavelength is 2\pi)
            stateVector: eigen vector obtained by diagonalisation of
                interaction Hamiltonian in a subspace given by the selected
                quasimomentum
            q (float): quasimomentum (in units of driving laser k)
            k (float): driving laser wavevector, define units for momentum and
                distance;
                if k==1 (default value), reciprocal lattice momentum is 2,
                and the full range of quasimomentum is from -1 to +1;
                one full wavelength is the 2\pi.

        Retruns:
            float:
        """

        index = len(stateVector) // 2 + 2  # Align Bloch functions in phase
        angle = np.angle(stateVector[index])
        sign = np.exp(-1j*angle)
        temp = 0 + 0j
        for l in np.arange(-self.lLimit, self.lLimit + 1, 1):
            temp += sign * stateVector[l + self.lLimit] \
                * np.exp(1.j * (2. * k * l + q) * x)
        return temp

    def BlochWavefunction(self,
                          trapPotentialDepth,
                          quasimomentum,
                          blochBandIndex):
        r"""
            Bloch wavefunction as a **function** of 1D coordinate.

            Example:
                Returns Bloch wavefunction. Use as following::

                    trapPotentialDepth = 40  # units of recoil energy
                    quasimomentum = 0
                    blochBandIndex = 0  # Bloch band lowest in energy is 0
                    wf = lattice.BlochWavefunction(trapPotentialDepth,
                                                   quasimomentum,
                                                   blochBandIndex)
                    wf(x)  # returns complex number corresponding to value of Bloch
                           # wavefunction at point x (cooridnate given in units of
                           # 1/k where k = 2 \pi / trapWavenegth )
                           # by default k=1, so one full wavelength is 2\pi

            Args:
                trapPotentialDepth (float): (in units of recoil energy
                    :obj:`OpticalLattice1D.getRecoilEnergy`)
                quasimomentum (float): (in units of 2 \pi /
                    :obj:`OpticalLattice1D.trapWavenegth`; note that
                    reciprocal lattice momentum in this units is 2, and that
                    full range of quasimomentum is from -1 to +1)

            Returns:
                Bloch wavefunction as a **function** of coordinate (see call
                example above)
        """
        temp1 = self.energy
        temp2 = self.quasimomentum
        temp3 = self.savedBlochBand
        self.diagonalise(trapPotentialDepth, [quasimomentum],
                           saveBandIndex = blochBandIndex)
        state = np.copy(self.savedBlochBand[0])

        self.energy = temp1
        self.quasimomenutm = temp2
        self.savedBlochBand = temp3
        return lambda x: self._BlochFunction(x, state, quasimomentum)


    def defineBasis(self, lLimit=35):
        """
            Define basis for Bloch band calculations

            Bloch states are calculated suming up all relevant states
            with momenta in range
            `[-lLimit * 4 * pi /trapWavenegth, +lLimit * 4 * pi /trapWavenegth]`
            Note that factor of 4 occurs since potential lattice period is
            twice the `trapWavelength` for standing wave.

            Args:
                lLimit (integer): Optional, defines maximal momentum to be taken
                    for calculation of Bloch States
                    as `lLimit * 4 * pi / trapWavenegth` . By default set to 35.
        """
        self.lLimit = lLimit

    def _getLatticeHamiltonian(self, q, Vlat):
        """
        Lattice Hamiltonian

        Args:
            q (float):
            Vlat (float):
            lLimit (int):
        """

        # assemble Hamiltonian
        hConstructor = [[], [], []]  # [[values],[columnIndex],[rowIndex]]
        for l in np.arange(- self.lLimit, self.lLimit + 1, 1):
            # basis index exp(2*l*k*x) state has index lLimit+l
            column = self.lLimit + l
            if (l - 1 >= - self.lLimit):
                hConstructor[0].append(- Vlat / 4.)
                hConstructor[1].append(column)
                hConstructor[2].append(column - 1)
            if (l + 1 <= self.lLimit):
                hConstructor[0].append(- Vlat / 4.)
                hConstructor[1].append(column)
                hConstructor[2].append(column + 1)
            # diagonal term
            # with global energy offset (- Vlat / 2.) factored out
            hConstructor[0].append((2. * l + q)**2 + Vlat / 2.)
            hConstructor[1].append(column)
            hConstructor[2].append(column)
        dimension = 2 * self.lLimit + 1
        hamiltonianQ = csr_matrix((hConstructor[0],
                                   (hConstructor[1], hConstructor[2])),
                                  shape=(dimension, dimension))
        return hamiltonianQ

    def diagonalise(self, trapPotentialDepth, quasimomentumList,
                    saveBandIndex=None):
        r"""
            Calculates energy levels (Bloch bands) for given `quasimomentumList`

            Energy levels and their quasimomentum are saved in internal variables
            `energy` and `quasimomentum`. Energies are saved in units of
            recoil energy, and quasimomentum in units of
            The optional parameter `saveBandIndex` specifies index of the Bloch
            band for which eigenvectrors should be saved. If provided,
            eigenvectors for each value `quasimomentumList[i]` are saved in
            `savedBlochBand[i]`.

            Args:
                latticePotential (float): lattice depth formed
                    by the standing wave of laser, with wavelength specified
                    during initialisation of the lattice
                    (in units of recoil energy).
                quasimomentumList (array): array of quasimomentum values for
                    which energy levels will be calculated (in units of
                    :math:`\hbar \cdot k`,
                    where :math:`k` is trapping laser wavevector;
                    since reciprocal lattice has twice the trapping laser
                    wavevector due to standing wave, full range of
                    quasimomentum is from -1 to +1)
                saveBandIndex (int): optional, default None. If provided,
                    specifies for which Bloch band should the eignevectors be
                    also saved. `saveBlochBand=0` corresponds to lowest energy
                    band.
        """

        self.energy = []
        self.quasimomentum = quasimomentumList
        self.savedBlochBand = []
        self.trapPotentialDepth = trapPotentialDepth
        for q in quasimomentumList:
            hamiltonianQ = self._getLatticeHamiltonian(q, trapPotentialDepth)
            ev, egvector = np.linalg.eig(hamiltonianQ.todense())
            egvector = np.transpose(np.array(egvector))
            orderInEnergy = np.argsort(ev)
            ev = ev[orderInEnergy]
            egvector = egvector[orderInEnergy]
            self.energy.append(ev)
            if saveBandIndex is not None:
                self.savedBlochBand.append(egvector[saveBandIndex])

    def plotLevelDiagram(self):
        """
        Plots energy level diagram (Bloch bands).

        Based on diagonalisation of the lattice potential, plots descrete
        eigen energy spectra obtained for each value of the quasimomentum
        used in :obj:`OpticalLattice1D.diagonalise` method.

        Returns:
            matploltib figure with a Bloch bands
        """
        f = plt.figure(figsize=(6, 10))
        ax = f.add_subplot(1, 1, 1)
        for i, energyLevels in enumerate(self.energy):
            ax.plot([self.quasimomentum[i]] * len(energyLevels),
                    energyLevels, ".", color="0.8")
        ax.set_xlabel(r"Quasimomentum, $q$ $(\hbar k)$")
        ax.set_ylabel(r"State energy, E ($E_{\rm r}$)")
        ax.set_ylim(-0.2, 50)
        ax.set_xlim(-1, 1)
        return f

    def getWannierFunction(self, x, latticeIndex=0, k=1):
        r"""
            Gives value at cooridnate x of a Wannier function localized
            at given lattice index.

            Args:
                x (float): spatial coordinate (in units of :math:`2\pi/k` ; for
                    default value of laser drivng wavevecto :math:`k=1` , one
                    trappinWavelength is :math:`2\pi` ). Coordinate origin is
                    at `latticeIndex=0` .
                latticeIndex (int): optional, lattice index at which the
                    Wannier function is localised. By defualt 0.
                k (float): optional; laser driving wavevector, defines unit
                    of length. Default value is 1, making one trapping laser
                    wavelenth equal to :math:`2\pi`
        """
        value = 0
        localizedAt = 2. * pi / k * latticeIndex / 2.
        # last division by 2 is because lattice period is
        # 2 x smaleler then wavelenth of the driving laser
        for i in range(len(self.quasimomentum)):
            q = self.quasimomentum[i]
            value += np.exp(-1j * q * localizedAt) \
                * self._BlochFunction(x,
                                      self.savedBlochBand[i],
                                      q, k=k)
        return value


class DynamicPolarizability:
    """
        Calculations of magic wavelengths and dynamic polarizability
        (scalar and tensor).


        Args:
            atom: alkali or alkaline element of choice
            n (int): principal quantum number of the selected stated
            l (int): orbital angular momentum of the selected state
            j (float): total angular momentum of selected state
            s (float): optional, spin state of the atom. Default value of
                0.5 is correct for Alkali atoms, but it has to be explicitly
                specified for DivalentAtom.
    """

    def __init__(self, atom, n, l, j, s=0.5):
        self.atom = atom
        self.n = n
        self.l = l
        self.j = j
        self.s = s

    def defineBasis(self, nMin, nMax):
        """
            Defines basis for calculation of dynamic polarizability

            Args:
                nMin (int): minimal principal quantum number of states to be
                    taken into account for calculation
                nMax (int): maxi,al principal quantum number of states to be
                    taken into account for calculation
        """
        self.nMin = nMin
        self.nMax = nMax

        self.basis = []
        self.lifetimes = []

        for n1 in np.arange(self.nMin, self.nMax + 1):
            lmin = self.l - 1
            if (lmin < - 0.1):
                lmin = self.l + 1
            for l1 in range(lmin, min(self.l + 2, n1)):
                j1 = l1 - self.s
                if j1 < 0.1:
                    j1 += 1
                while j1 <= l1 + self.s + 0.1:
                    if self.__isDipoleCoupled(
                        self.n, self.l, self.j,
                        n1, l1, j1
                            ):
                        # print([n1, l1, j1, self.s])
                        self.basis.append([n1, l1, j1, self.s])
                    j1 += 1

        for state in self.atom.extraLevels:
            if ((len(state) == 3 or abs(state[3] - self.s) < 0.1)
                and
                self.__isDipoleCoupled(
                    self.n, self.l, self.j,
                    state[0], state[1], state[2])
                    ):
                self.basis.append(state)


    def __isDipoleCoupled(self,
                          n1, l1, j1,
                          n2, l2, j2,
                          s=0.5):
        if ( not (abs(l1 - l2) != 1
                and( (abs(j1 - 0.5) < 0.1
                      and abs(j2 - 0.5) < 0.1) # j = 1/2 and j'=1/2 forbidden
                      or
                      (abs(j1) < 0.1
                       and abs(j2 - 1) < 0.1)  # j = 0 and j'=1 forbidden
                      or
                      (abs(j1-1) < 0.1
                       and abs(j2) < 0.1)  # j = 1 and j'=0 forbidden
                   )
                )
                and not(abs(j1)<0.1 and abs(j2)<0.1)  # j = 0 and j'=0 forbiden
                and not (abs(l1)<0.1 and abs(l2)<0.1) # l = 0 and l' = 0 is forbiden
                ):
            dl = abs(l1 - l2)
            dj = abs(j1 - j2)
            if dl == 1 and (dj < 1.1):
                return True
            else:
                return False
        return False


    def getPolarizability(self, driveWavelength,
                          units="SI",
                          accountForStateLifetime=False,
                          mj=None
                          ):
        r"""
            Calculates of scalar, vector, tensor, core and pondermotive
            polarizability, and returns state corresponding to the closest
            transition resonance.

           Note that pondermotive polarisability is calculated as
           :math:`\alpha_P = e^2 / (2 m_e \omega^2)`, i.e. assumes that the
           definition of the energy shift in field :math:`E` is
           :math:`\frac{1}{2}\alpha_P E^2`. For more datils check the
           preprint  `arXiv:2007.12016`_ that introduced the update.

           .. _`arXiv:2007.12016`:
               https://arxiv.org/abs/2007.12016

            Args:
                driveWavelength (float): wavelength of driving field
                    (in units of m)
                units (string): optional, 'SI' or 'a.u.' (equivalently 'au'),
                    switches between SI units for returned result
                    (:math:`Hz V^-2 m^2` )
                    and atomic units (":math:`a_0^3` "). Defaul 'SI'
                accountForStateLifetime (bool): optional, should we account
                    for finite transition linewidths caused by finite state
                    lifetimes. By default False.
            Returns:
                scalar, vector, tensor, pondermotive polarisability of state,
                core polarisability and atomic state whose resonance is closest
                in energy. Returned units depend on `units` parameter
                (default SI).
        """

        if (accountForStateLifetime and len(self.lifetimes) == 0):
            for state in self.basis:
                self.lifetimes.append(self.atom.getStateLifetime(state[0],
                                                                 state[1],
                                                                 state[2],
                                                                 s=self.s))

        driveEnergy = C_c / driveWavelength * C_h
        initialLevelEnergy = self.atom.getEnergy(self.n, self.l, self.j,
                                                 s=self.s) * C_e

        # prefactor for vector polarisability
        prefactor1 = 1. / ((self.j + 1) * (2 * self.j + 1))

        # prefactor for tensor polarisability
        prefactor2 = (6 * self.j * (2 * self.j - 1)
                      / (6 * (self.j + 1)
                         * (2 * self.j + 1)
                         * (2 * self.j + 3))
                      )**0.5

        alpha0 = 0.
        alpha1 = 0.
        alpha2 = 0.
        closestState = []
        closestEnergy = -1

        targetStateLifetime = self.atom.getStateLifetime(self.n, self.l,
                                                         self.j, s=self.s)

        for i, state in enumerate(self.basis):
            n1 = state[0]
            l1 = state[1]
            j1 = state[2]

            if ((mj is None) or (abs(mj) < j1 + 0.1)):

                if abs(j1 - self.j) < 1.1 and (abs(l1 - self.l) > 0.5
                                               and abs(l1 - self.l) < 1.1):
                    coupledLevelEnergy = self.atom.getEnergy(n1, l1, j1,
                                                             s=self.s) * C_e

                    diffEnergy = abs((coupledLevelEnergy
                                      - initialLevelEnergy)**2 - driveEnergy**2)
                    if ((diffEnergy < closestEnergy) or (closestEnergy < 0)
                        ):
                        closestEnergy = diffEnergy
                        closestState = state

                    if diffEnergy < 1e-65:
                        # print("For given frequency we are in exact resonance with state %s" % printStateString(n1,l1,j1,s=s))
                        return None, None, None, None, None, state

                    # common factors
                    if accountForStateLifetime:
                        transitionLinewidth = (1 / self.lifetimes[i]
                                               + 1 / targetStateLifetime) * C_h
                    else:
                        transitionLinewidth = 0.

                    # transitionEnergy
                    transitionEnergy = (coupledLevelEnergy
                                        - initialLevelEnergy)


                    d = self.atom.getReducedMatrixElementJ(self.n, self.l, self.j,
                                                               n1, l1, j1,
                                                               s=self.s)**2 \
                            * (C_e * physical_constants["Bohr radius"][0])**2\
                            * transitionEnergy \
                            * (transitionEnergy**2 - driveEnergy**2
                               + transitionLinewidth**2 / 4) \
                            / ((transitionEnergy**2 - driveEnergy**2
                                + transitionLinewidth**2 / 4)**2
                               + transitionLinewidth**2 * driveEnergy**2)

                    alpha0 += d

                    # vector polarsizavility
                    alpha1 += (-1) * (self.j * (self.j+1) + 2 - j1 * (j1 + 1)) \
                        * self.atom.getReducedMatrixElementJ(self.n,
                                                             self.l,
                                                             self.j,
                                                             n1, l1, j1,
                                                             s=self.s)**2\
                        * (C_e * physical_constants["Bohr radius"][0])**2\
                        * driveEnergy \
                        * (transitionEnergy**2 - driveEnergy**2
                           - transitionLinewidth**2 / 4) \
                         / ((transitionEnergy**2 - driveEnergy**2
                             + transitionLinewidth**2 / 4)**2
                            + transitionLinewidth**2 * driveEnergy**2)

                    # tensor polarizability vanishes for j=1/2 and j=0 states
                    # because Wigner6j is then zero
                    if self.j > 0.6:
                        alpha2 += \
                            (- 1)**(self.j + j1 + 1) \
                            * self.atom.getReducedMatrixElementJ(self.n,
                                                                 self.l,
                                                                 self.j,
                                                                 n1, l1, j1,
                                                                 s=self.s)**2 \
                            * (C_e * physical_constants["Bohr radius"][0])**2\
                            * Wigner6j(self.j, 1, j1, 1, self.j, 2) \
                            * (coupledLevelEnergy - initialLevelEnergy) \
                            / ((coupledLevelEnergy - initialLevelEnergy)**2
                               - driveEnergy**2)

        alpha0 = 2. * alpha0/(3. * (2. * self.j + 1.))
        alpha0 = alpha0 / C_h  # Hz m^2 / V^2

        alpha1 = prefactor1 * alpha1 / C_h

        alpha2 = - 4 * prefactor2 * alpha2 / C_h

        # core polarizability -> assumes static polarisability
        alphaC = self.atom.alphaC * 2.48832e-8  # convert to Hz m^2 / V^2

        # podermotive shift
        driveOmega = 2 * np.pi / driveWavelength * C_c
        alphaP = C_e**2 / (2 * C_m_e * driveOmega**2 * C_h)

        if (units == "SI"):
            return alpha0, alpha1, alpha2, alphaC, alphaP, closestState   # in Hz m^2 / V^2
        elif (units == "a.u." or units == "au"):
            return alpha0 / 2.48832e-8, alpha1 / 2.48832e-8, alpha2 / 2.48832e-8, \
                alphaC / 2.48832e-8, alphaP / 2.48832e-8, closestState
        else:
            raise ValueError("Only 'SI' and 'a.u' (atomic units) are recognised"
                             " as 'units' parameter. Entered value '%s' is"
                             " not recognised." % units)

    def plotPolarizability(self, wavelengthList,
                           mj=None,
                           addToPlotAxis=None,
                           line="b-",
                           units="SI",
                           addCorePolarisability=True,
                           addPondermotivePolarisability=False,
                           accountForStateLifetime=False,
                           debugOutput=False):
        r"""
        Plots of polarisability for a range of wavelengths.

        Can be combined for different states to allow finding magic wavelengths
        for pairs of states. Currently supports only driving with
        linearly polarised light. See example
        `magic wavelength snippet`_.

        .. _`magic wavelength snippet`:
            ./ARC_3_0_introduction.html#Calculations-of-dynamic-polarisability-and-magic-wavelengths-for-optical-traps


        Args:
            wavelengthList (array): wavelengths for which we want to calculate
                polarisability (in units of m).
            mj (float): optional, `mj` projection of the total angular
                momenutum for the states for which we are calculating
                polarisability. By default it's `+j`.
            line (string): optional, line style short definition to be passed
                to matplotlib when plotting calculated polarisabilities
            units (string): optional, 'SI' or 'a.u.' (equivalently 'au'),
                switches between SI units for returned result
                (:math:`Hz V^-2 m^2` )
                and atomic units (":math:`a_0^3` "). Deafault 'SI'.
            addCorePolarisability (bool): optional, should ionic core
                polarisability be taken into account. By default True.
            addPondermotivePolarisability (bool): optional, should pondermotive
                polarisability (also called free-electron polarisability)
                be added to the total polarisability. Default is
                False. It assumes that there is no significant variation of
                trapping field intensity over the range of the electric cloud.
                If this condition is not satisfied, one has to calculate
                total shift as average over the electron wavefunction.
            accountForStateLifetime (bool): optional, should we account
                for finite transition linewidths caused by finite state
                lifetimes. By default False.
            debugOutput (bool): optonal. Print additional output on resonances
                Default value False.
        """

        pFinal = []
        wFinal = []
        p = []
        w = []
        resonances = []

        if (mj is None):
            mj = self.j

        if (self.j > 0.5 + 0.1):
            tensorPrefactor = (3 * mj**2 - self.j * (self.j + 1)) / \
                (self.j * (2 * self.j - 1))
        else:
            tensorPrefactor = 0

        for wavelength in wavelengthList:
            scalarP, vectorP, tensorP, coreP, pondermotiveP, state = self.getPolarizability(
                wavelength,
                accountForStateLifetime=accountForStateLifetime,
                units=units,
                mj=mj)
            if (scalarP is not None):
                # we are not hitting directly the resonance
                totalP = scalarP + tensorPrefactor * tensorP
                if addCorePolarisability:
                    totalP += coreP
                if addPondermotivePolarisability:
                    totalP += pondermotiveP
                if ((len(p) > 0) and p[-1] * totalP < 0
                    and (len(p) > 2 and (p[-2] - p[-1]) * totalP > 0)
                        ):
                    pFinal.append(p)
                    wFinal.append(w)
                    p = []
                    w = []
                    resonances.append(wavelength)
                    if debugOutput:
                        print(r"Resonance: %.2f nm %s"
                              % (wavelength * 1e9,
                                 printStateString(state[0],
                                                  state[1],
                                                  state[2],
                                                  s=self.s))
                             )
                p.append(totalP)
                w.append(wavelength)

        pFinal.append(p)
        wFinal.append(w)

        if addToPlotAxis is None:
            fig = plt.figure()
            ax = fig.add_subplot(1, 1, 1)
        else:
            ax = addToPlotAxis
        for i in range(len(wFinal)):
            ax.plot(np.array(wFinal[i]) * 1e9, pFinal[i], line,
                    zorder=1)
            ax.set_xlabel(r"Driving field wavelength (nm)")
            if units == "SI":
                ax.set_ylabel(r"Polarizability (Hz/V$^2$ cm$^2$)")
            else:
                ax.set_ylabel(r"Polarizability (a.u.)")
            for resonance in resonances:
                ax.axvline(x=resonance * 1e9, linestyle=":", color="0.5",
                           zorder=0)
        return ax
