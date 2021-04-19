from arc import *
atom = Rubidium87()

pair = \
PairStateInteractions(atom,
                      70, 1, 1.5,
                      70, 1, 1.5,
                      1.5,1.5,5)
LeRoy70Rb = pair.getLeRoyRadius()
LeRoy70Rb

calculation = StarkMapResonances(atom,[70,1,1.5,1.5],atom,[70,1,1.5,1.5])

calculation.findResonances(60,80,20,np.linspace(0,100,100),Bz=0,progressOutput=True)