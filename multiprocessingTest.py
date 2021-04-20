from arc import *
import multiprocessing
import os



atom = Rubidium87()
stark = StarkMap(atom)
nlj = (70, 1, 1.5)
nljm = (70, 1, 1.5, 1.5)
# stark.defineBasis(*nljm, 60, 80, 15)
# stark.diagonalise(np.linspace(0, 100, 100), progressOutput=True)


def starkmapDiag(nljm, nmax, nmin, lmax, eRange):
    print("Worker process id : {0}".format(os.getpid()))
    atom = Rubidium87()
    sm = StarkMap(atom)
    # sm.defineBasis((*nljm, nmin, nmax, lmax))
    # sm.diagonalise(eRange, progressOutput=True)
    return atom.getEnergy(70,0,0.5)




if __name__ == '__main__':
    pool = multiprocessing.Pool(processes=4)
    inputs = [(nljm, 80, 60, 15, np.linspace(0, 100, 100)),
              (nljm, 80, 60, 15, np.linspace(0, 100, 100)),
              (nljm, 80, 60, 15, np.linspace(0, 100, 100))]
    outputs = pool.starmap(starkmapDiag, inputs, chunksize=1)
    print(outputs)