from arc import *
import multiprocessing
import os
import numpy as np
import ctypes as c
import multiprocessingTestMyGlobal
multiprocessingTestMyGlobal.data = [5]

def ARCTEST():
    atom = Rubidium87()
    stark = StarkMap(atom)
    nlj = (70, 1, 1.5)
    nljm = (70, 1, 1.5, 1.5)


    stark.defineBasis(*nljm, 60, 80, 15)
    [stark.diagonalise(np.linspace(0, 100, 201), progressOutput=True,cores = core) for core
     in [1,2,3,4,5,6,7,8,9,10,11,12]]
    stark.plotLevelDiagram()
    stark.ax.set_ylim([-25,-23])
    stark.ax.text(0.6, 0.9, "Multiprocessor = 8",
                  weight='bold',fontsize = 12,
                horizontalalignment='left',
                verticalalignment='top',
                transform=stark.ax.transAxes)
    stark.showPlot()

    stark2 = StarkMap(atom)
    stark2.defineBasis(*nljm, 60, 80, 15)
    stark2.diagonalise(np.linspace(0, 100, 201), progressOutput=True,cores = 8,parallel=False)
    stark2.plotLevelDiagram()
    stark2.ax.set_ylim([-25,-23])
    stark2.ax.text(0.8, 0.8, "Original serial code",
                  weight='bold',fontsize = 12,
                horizontalalignment='left',
                verticalalignment='top',
                transform=stark2.ax.transAxes)
    stark2.showPlot()


def starkmapDiag(nljm, nmax, nmin, lmax, eRange):
    print("Worker process id : {0}".format(os.getpid()))
    # atom = Rubidium87()
    # sm = StarkMap(atom)
    # sm.defineBasis((*nljm, nmin, nmax, lmax))
    # sm.diagonalise(eRange, progressOutput=True)
    # return atom.getEnergy(70,0,0.5)


def multiproc():
    pool = multiprocessing.Pool(processes=4)
    inputs = [(nljm, 80, 60, 15, np.linspace(0, 100, 100)),
              (nljm, 80, 60, 15, np.linspace(0, 100, 100)),
              (nljm, 80, 60, 15, np.linspace(0, 100, 100))]
    outputs = pool.starmap(starkmapDiag, inputs, chunksize=1)
    print(outputs)


def square(x,y):
    return x * y + multiprocessingTestMyGlobal.data[0][4]

def initProcess(share):
  multiprocessingTestMyGlobal.data = [share[0],share[1]]


class test():
    def __init__(self):
        0

    def methodA(self):
        a = 5
        # multiprocessingTestMyGlobal.data = [2,3]
        n, m = 2, 3
        mp_arr = multiprocessing.Array(c.c_double, n * m)  # shared, can be used from multiple processes
        mp_arr2 = multiprocessing.Array(c.c_double, 0)  # shared, can be used from multiple processes
        # then in each new process create a new numpy array using:
        arr = np.frombuffer(mp_arr.get_obj())  # mp_arr and arr share the same memory
        # make it two-dimensional
        b = arr.reshape((n, m))  # b and arr share the same memory

        mp_arr = np.array([1,2,3,4,100,6])
        mp_arr2 = np.array([1, 2, 3, 4, 100, 6])

        pool = multiprocessing.Pool(processes=4,initializer=initProcess,initargs=([mp_arr,mp_arr2],))
        mp_arr = np.array([1, 2, 3, 4, 5, 6])
        inputs = [[0,0], [1,1], [2,2], [3,3], [4,4]]
        outputs = pool.starmap(square, inputs)
        print(outputs)


if __name__ == '__main__':
    t = test()
    # t.methodA()
    # ARCTEST()
    # timeToPrep = [0.99,1.97,2.90,3.86,4.84,5.80,6.78,7.78,8.75,9.73,10.67,11.63]
    # timeForCalc = [36.63,21.83,16.86,15.60,15.09,15.81,15.36,15.67,16.25,16.95,17.47,18.49]
    # cores = [1,2,3,4,5,6,7,8,9,10,11,12]
    # fig,ax = plt.subplots(figsize = [8,6])
    # ax.plot()