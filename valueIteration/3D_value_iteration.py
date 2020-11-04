import heterocl as hcl
#from Grid.GridProcessing import Grid
import numpy as np
import time
#from user_definer import *




####################################### USER-DEFINED VALUES ########################################


_bounds     = np.array([[-5.0, 5.0],[-3.0, 3.0],[10, 15]])
_ptsEachDim = np.array([40, 40, 50])
_actions    = np.array([[0.5,0,0], [0,1,0], [0,0,1.1]])
_gamma      = np.array([0.9])
_epsilon    = np.array([.0000005])
_maxIters   = np.array([500])
_trans      = np.zeros([2, 4]) # size: [maximum number of transition states available x 4]
_useNN      = np.array([1])


###################################### USER-DEFINED FUNCTIONS ######################################


# Given state and action, return successor states and their probabilities
# sVals: the coordinates of state
def transition(sVals, action, trans):
    trans[0, 0] = 0.9
    trans[1, 0] = 0.1
    trans[0, 1] = sVals[0] + action[0]
    trans[0, 2] = sVals[1] + action[1]
    trans[0, 3] = sVals[2] + action[2]
    trans[1, 1] = sVals[0]
    trans[1, 2] = sVals[1]
    trans[1, 3] = sVals[2]


# Return the reward for taking action from state
def reward(sVals, action):
    rwd = hcl.scalar(0, "rwd")
    with hcl.if_(hcl.and_(sVals[0] == 8, sVals[1] == 8, sVals[2] == 8)): rwd[0] = 100
    with hcl.else_():                                                    rwd[0] = 1
    return rwd[0]



######################################### HELPER FUNCTIONS #########################################


# Update the value function at position (i,j,k)
def updateVopt(i, j, k, iVals, sVals, actions, Vopt, intermeds, trans, interpols, gamma, bounds, ptsEachDim, useNN):
    with hcl.for_(0, actions.shape[0], name="a") as a:
        # set iVals equal to (i,j,k) and sVals equal to the corresponding state values at (i,j,k)
        updateStateVals(i, j, k, iVals, sVals, bounds, ptsEachDim)
        # call the transition function to obtain the outcome(s) of action a from state (si,sj,sk)
        transition(sVals, actions[a], trans)
        # initialize the value of the action using the immediate reward of taking that action
        intermeds[a] = reward(sVals, actions[a])
        # add the value of each possible successor state
        with hcl.for_(0, trans.shape[0], name="si") as si:
            p        = trans[si,0]
            sVals[0] = trans[si,1]
            sVals[1] = trans[si,2]
            sVals[2] = trans[si,3]
            # convert the state values of the successor state (si,sj,sk) into indeces (ia, ij, ik)
            stateToIndex(sVals, iVals, bounds, ptsEachDim)

            #NOTE: nearest neighbour
            with hcl.if_(useNN[0] == 1):
                # if (ia, ij, ik) is within the state space, add its discounted value to action a
                with hcl.if_(hcl.and_(iVals[0] < Vopt.shape[0], iVals[1] < Vopt.shape[1], iVals[2] < Vopt.shape[2])):
                    with hcl.if_(hcl.and_(iVals[0] >= 0, iVals[1] >= 0, iVals[2] >= 0)):
                        intermeds[a] += (gamma[0] * (p * Vopt[iVals[0], iVals[1], iVals[2]]))

            #NOTE: interpolation
            with hcl.if_(useNN[0] == 0):
                stateToIndexInterpolants(sVals, bounds, ptsEachDim, interpols)
                with hcl.for_(0, interpols.shape[0], name="ipl") as ipl:
                    iplWeight = interpols[ipl, 0]
                    iVals[0]  = interpols[ipl, 1]
                    iVals[1]  = interpols[ipl, 2]
                    iVals[2]  = interpols[ipl, 3]

                    # if (ia, ij, ik) is within the state space, add its discounted value to action a
                    with hcl.if_(hcl.and_(iVals[0] < Vopt.shape[0], iVals[1] < Vopt.shape[1], iVals[2] < Vopt.shape[2])):
                        with hcl.if_(hcl.and_(iVals[0] >= 0, iVals[1] >= 0, iVals[2] >= 0)):
                            intermeds[a] += (gamma[0] * iplWeight * (p * Vopt[iVals[0], iVals[1], iVals[2]]))

    # maximize over each possible action in intermeds to obtain the optimal value
    with hcl.for_(0, intermeds.shape[0], name="r") as r:
        with hcl.if_(Vopt[i,j,k] < intermeds[r]):
            Vopt[i,j,k] = intermeds[r]


# Returns 0 if convergence has been reached
def evaluateConvergence(newV, oldV, epsilon, reSweep):
    delta = hcl.scalar(0, "delta")
    # Calculate the difference, if it's negative, make it positive
    delta[0] = newV[0] - oldV[0]
    with hcl.if_(delta[0] < 0):
        delta[0] = delta[0] * -1
    with hcl.if_(delta[0] > epsilon[0]):
        reSweep[0] = 1


# convert state values into indeces using nearest neighbour
def stateToIndex(sVals, iVals, bounds, ptsEachDim):
    iVals[0] = (sVals[0] - bounds[0,0]) / ( (bounds[0,1] - bounds[0,0]) / ptsEachDim[0] )
    iVals[1] = (sVals[1] - bounds[1,0]) / ( (bounds[1,1] - bounds[1,0]) / ptsEachDim[1] )
    iVals[2] = (sVals[2] - bounds[2,0]) / ( (bounds[2,1] - bounds[2,0]) / ptsEachDim[2] )
    # NOTE: add 0.5 to simulate rounding
    iVals[0] = hcl.cast(hcl.Int(), iVals[0] + 0.5)
    iVals[1] = hcl.cast(hcl.Int(), iVals[1] + 0.5)
    iVals[2] = hcl.cast(hcl.Int(), iVals[2] + 0.5)


# given state values sVals, obtain the 8 possible successor states and their corresponding weight
def stateToIndexInterpolants(sVals, bounds, ptsEachDim, interpols):
    # obtain index values (not rounded)
    ia = (sVals[0] - bounds[0,0]) / ( (bounds[0,1] - bounds[0,0]) / ptsEachDim[0] )
    ja = (sVals[1] - bounds[1,0]) / ( (bounds[1,1] - bounds[1,0]) / ptsEachDim[1] )
    ka = (sVals[2] - bounds[2,0]) / ( (bounds[2,1] - bounds[2,0]) / ptsEachDim[2] )

    # obtain the 8 nearest states
    iMin = hcl.cast(hcl.Int(), ia)
    jMin = hcl.cast(hcl.Int(), ja)
    kMin = hcl.cast(hcl.Int(), ka)
    iMax = hcl.cast(hcl.Int(), ia + 1.0)
    jMax = hcl.cast(hcl.Int(), ja + 1.0)
    kMax = hcl.cast(hcl.Int(), ka + 1.0) 

    # assign values
    interpols[0, 1] = iMin
    interpols[0, 2] = jMin
    interpols[0, 3] = kMin

    interpols[1, 1] = iMax
    interpols[1, 2] = jMax
    interpols[1, 3] = kMax

    interpols[2, 1] = iMax
    interpols[2, 2] = jMin
    interpols[2, 3] = kMin

    interpols[3, 1] = iMin
    interpols[3, 2] = jMax
    interpols[3, 3] = kMin

    interpols[4, 1] = iMin
    interpols[4, 2] = jMin
    interpols[4, 3] = kMax

    interpols[5, 1] = iMax
    interpols[5, 2] = jMax
    interpols[5, 3] = kMin

    interpols[6, 1] = iMax
    interpols[6, 2] = jMin
    interpols[6, 3] = kMax

    interpols[7, 1] = iMin
    interpols[7, 2] = jMax
    interpols[7, 3] = kMax

    # set the weights of the 8 nearest states
    w1 = 1 - ( absdiff(ia, iMin) + absdiff(ja, jMin) + absdiff(ka, kMin) ) / 3  #w1 iMin, jMin, kMin
    w2 = 1 - ( absdiff(ia, iMax) + absdiff(ja, jMax) + absdiff(ka, kMax) ) / 3  #w2 iMax, jMax, kMax
    w3 = 1 - ( absdiff(ia, iMax) + absdiff(ja, jMin) + absdiff(ka, kMin) ) / 3  #w3 iMax, jMin, kMin
    w4 = 1 - ( absdiff(ia, iMin) + absdiff(ja, jMax) + absdiff(ka, kMin) ) / 3  #w4 iMin, jMax, kMin
    w5 = 1 - ( absdiff(ia, iMin) + absdiff(ja, jMin) + absdiff(ka, kMax) ) / 3  #w5 iMin, jMin, kMax
    w6 = 1 - ( absdiff(ia, iMax) + absdiff(ja, jMax) + absdiff(ka, kMin) ) / 3  #w6 iMax, jMax, kMin
    w7 = 1 - ( absdiff(ia, iMax) + absdiff(ja, jMin) + absdiff(ka, kMax) ) / 3  #w7 iMax, jMin, kMax
    w8 = 1 - ( absdiff(ia, iMin) + absdiff(ja, jMax) + absdiff(ka, kMax) ) / 3  #w8 iMin, jMax, kMax

    total = w1
    total += w2
    total += w3
    total += w4
    total += w5
    total += w6
    total += w7
    total += w8

    interpols[0, 0] = w1 / total
    interpols[1, 0] = w2 / total
    interpols[2, 0] = w3 / total
    interpols[3, 0] = w4 / total
    interpols[4, 0] = w5 / total
    interpols[5, 0] = w6 / total
    interpols[6, 0] = w7 / total
    interpols[7, 0] = w8 / total 

    
# convert indices into state values
def indexToState(iVals, sVals, bounds, ptsEachDim): 
    sVals[0] = (iVals[0] / ptsEachDim[0]) * (bounds[0,1] - bounds[0,0]) + bounds[0,0]
    sVals[1] = (iVals[1] / ptsEachDim[1]) * (bounds[1,1] - bounds[1,0]) + bounds[1,0]
    sVals[2] = (iVals[2] / ptsEachDim[2]) * (bounds[2,1] - bounds[2,0]) + bounds[2,0]


# set iVals equal to (i,j,k) and sVals equal to the corresponding state values at (i,j,k)
def updateStateVals(i, j, k, iVals, sVals, bounds, ptsEachDim):
    iVals[0] = i
    iVals[1] = j
    iVals[2] = k
    indexToState(iVals, sVals, bounds, ptsEachDim)


# TODO: move outside of this file
def absdiff(x, y):
    z = x - y
    with hcl.if_(z < 0):
        z = z * (-1)
    return z


######################################### VALUE ITERATION ##########################################


# Minh: All functions defined within solve_Vopt needs to be re-written as heteroCL (hcl.while, etc)
# Minh: Also arrays values used and passed into solve_Vopt function needs to be placeholder type
def value_iteration_3D():
    def solve_Vopt(Vopt, actions, intermeds, trans, interpols, gamma, epsilon, iVals, sVals, bounds, ptsEachDim, count, maxIters, useNN):
            reSweep = hcl.scalar(1, "reSweep")
            oldV    = hcl.scalar(0, "oldV")
            newV    = hcl.scalar(0, "newV")
            with hcl.while_(hcl.and_(reSweep[0] == 1, count[0] < maxIters[0])):
                reSweep[0] = 0

                # Perform value iteration by sweeping in direction 1
                with hcl.Stage("Sweep_1"):
                    with hcl.for_(0, Vopt.shape[0], name="i") as i:
                        with hcl.for_(0, Vopt.shape[1], name="j") as j:
                            with hcl.for_(0, Vopt.shape[2], name="k") as k:
                                oldV[0] = Vopt[i,j,k]
                                updateVopt(i, j, k, iVals, sVals, actions, Vopt, intermeds, trans, interpols, gamma, bounds, ptsEachDim, useNN)
                                newV[0] = Vopt[i,j,k]
                                evaluateConvergence(newV, oldV, epsilon, reSweep)
                    count[0] += 1

                # Perform value iteration by sweeping in direction 2
                with hcl.Stage("Sweep_2"):
                    with hcl.for_(1, Vopt.shape[0] + 1, name="i") as i:
                        with hcl.for_(1, Vopt.shape[1] + 1, name="j") as j:
                            with hcl.for_(1, Vopt.shape[2] + 1, name="k") as k:
                                i2 = Vopt.shape[0] - i
                                j2 = Vopt.shape[1] - j
                                k2 = Vopt.shape[2] - k
                                oldV[0] = Vopt[i2,j2,k2]
                                updateVopt(i2, j2, k2, iVals, sVals, actions, Vopt, intermeds, trans, interpols, gamma, bounds, ptsEachDim, useNN)
                                newV[0] = Vopt[i2,j2,k2]
                                evaluateConvergence(newV, oldV, epsilon, reSweep)
                    count[0] += 1

                # Perform value iteration by sweeping in direction 3
                with hcl.Stage("Sweep_3"):
                    with hcl.for_(1, Vopt.shape[0] + 1, name="i") as i:
                        with hcl.for_(0, Vopt.shape[1], name="j") as j:
                            with hcl.for_(0, Vopt.shape[2], name="k") as k:
                                i2 = Vopt.shape[0] - i
                                oldV[0] = Vopt[i2,j,k]
                                updateVopt(i2, j, k, iVals, sVals, actions, Vopt, intermeds, trans, interpols, gamma, bounds, ptsEachDim, useNN)
                                newV[0] = Vopt[i2,j,k]
                                evaluateConvergence(newV, oldV, epsilon, reSweep)
                    count[0] += 1

                # Perform value iteration by sweeping in direction 4
                with hcl.Stage("Sweep_4"):
                    with hcl.for_(0, Vopt.shape[0], name="i") as i:
                        with hcl.for_(1, Vopt.shape[1] + 1, name="j") as j:
                            with hcl.for_(0, Vopt.shape[2], name="k") as k:
                                j2 = Vopt.shape[1] - j
                                oldV[0] = Vopt[i,j2,k]
                                updateVopt(i, j2, k, iVals, sVals, actions, Vopt, intermeds, trans, interpols, gamma, bounds, ptsEachDim, useNN)
                                newV[0] = Vopt[i,j2,k]
                                evaluateConvergence(newV, oldV, epsilon, reSweep)
                    count[0] += 1

                # Perform value iteration by sweeping in direction 5
                with hcl.Stage("Sweep_5"):
                    with hcl.for_(0, Vopt.shape[0], name="i") as i:
                        with hcl.for_(0, Vopt.shape[1], name="j") as j:
                            with hcl.for_(1, Vopt.shape[2] + 1, name="k") as k:
                                k2 = Vopt.shape[2] - k
                                oldV[0] = Vopt[i,j,k2]
                                updateVopt(i, j, k2, iVals, sVals, actions, Vopt, intermeds, trans, interpols, gamma, bounds, ptsEachDim, useNN)
                                newV[0] = Vopt[i,j,k2]
                                evaluateConvergence(newV, oldV, epsilon, reSweep)
                    count[0] += 1

                # Perform value iteration by sweeping in direction 6
                with hcl.Stage("Sweep_6"):
                    with hcl.for_(1, Vopt.shape[0] + 1, name="i") as i:
                        with hcl.for_(1, Vopt.shape[1] + 1, name="j") as j:
                            with hcl.for_(0, Vopt.shape[2], name="k") as k:
                                i2 = Vopt.shape[0] - i
                                j2 = Vopt.shape[1] - j
                                oldV[0] = Vopt[i2,j2,k]
                                updateVopt(i2, j2, k, iVals, sVals, actions, Vopt, intermeds, trans, interpols, gamma, bounds, ptsEachDim, useNN)
                                newV[0] = Vopt[i2,j2,k]
                                evaluateConvergence(newV, oldV, epsilon, reSweep)
                    count[0] += 1

                # Perform value iteration by sweeping in direction 7
                with hcl.Stage("Sweep_7"):
                    with hcl.for_(1, Vopt.shape[0] + 1, name="i") as i:
                        with hcl.for_(0, Vopt.shape[1], name="j") as j:
                            with hcl.for_(1, Vopt.shape[2] + 1, name="k") as k:
                                i2 = Vopt.shape[0] - i
                                k2 = Vopt.shape[2] - k
                                oldV[0] = Vopt[i2,j,k2]
                                updateVopt(i2, j, k2, iVals, sVals, actions, Vopt, intermeds, trans, interpols, gamma, bounds, ptsEachDim, useNN)
                                newV[0] = Vopt[i2,j,k2]
                                evaluateConvergence(newV, oldV, epsilon, reSweep)
                    count[0] += 1

                # Perform value iteration by sweeping in direction 8
                with hcl.Stage("Sweep_8"):
                    with hcl.for_(0, Vopt.shape[0], name="i") as i:
                        with hcl.for_(1, Vopt.shape[1] + 1, name="j") as j:
                            with hcl.for_(1, Vopt.shape[2] + 1, name="k") as k:
                                j2 = Vopt.shape[1] - j
                                k2 = Vopt.shape[2] - k
                                oldV[0] = Vopt[i,j2,k2]
                                updateVopt(i, j2, k2, iVals, sVals, actions, Vopt, intermeds, trans, interpols, gamma, bounds, ptsEachDim, useNN)
                                newV[0] = Vopt[i,j2,k2]
                                evaluateConvergence(newV, oldV, epsilon, reSweep)
                    count[0] += 1



    ###################################### SETUP PLACEHOLDERS ######################################
    
    # Initialize the HCL environment
    hcl.init()
    hcl.config.init_dtype = hcl.Float()

    # NOTE: trans is a tensor with size = maximum number of transitions
    # NOTE: intermeds must have size  [# possible actions]
    # NOTE: transition must have size [# possible outcomes, #state dimensions + 1]
    Vopt       = hcl.placeholder(tuple(_ptsEachDim), name="Vopt", dtype=hcl.Float())
    gamma      = hcl.placeholder((0,), "gamma")
    count      = hcl.placeholder((0,), "count")
    maxIters   = hcl.placeholder((0,), "maxIters")
    epsilon    = hcl.placeholder((0,), "epsilon")
    actions    = hcl.placeholder(tuple(_actions.shape), name="actions", dtype=hcl.Float())
    intermeds  = hcl.placeholder(tuple([3]), name="intermeds", dtype=hcl.Float())
    trans      = hcl.placeholder(tuple([2,4]), name="successors", dtype=hcl.Float())
    bounds     = hcl.placeholder(tuple([3, 2]), name="bounds", dtype=hcl.Float())
    ptsEachDim = hcl.placeholder(tuple([3]), name="ptsEachDim", dtype=hcl.Float())
    sVals      = hcl.placeholder(tuple([3]), name="sVals", dtype=hcl.Float())
    iVals      = hcl.placeholder(tuple([3]), name="iVals", dtype=hcl.Float())

    # required for linear interpolation
    interpols  = hcl.placeholder(tuple([8, 4]), name="interpols", dtype=hcl.Float())
    useNN      = hcl.placeholder((0,), "useNN")

    # Create a static schedule -- graph
    s = hcl.create_schedule([Vopt, actions, intermeds, trans, interpols, gamma, epsilon, iVals, sVals, bounds, ptsEachDim, count, maxIters, useNN], solve_Vopt)
    

    ########################################## INITIALIZE ##########################################

    # Convert the python array to hcl type array
    V_opt     = hcl.asarray(np.zeros(_ptsEachDim))
    intermeds = hcl.asarray(np.ones([3]))
    trans     = hcl.asarray(_trans)
    gamma     = hcl.asarray(_gamma)
    epsilon   = hcl.asarray(_epsilon)
    count     = hcl.asarray(np.zeros(1))
    maxIters  = hcl.asarray(_maxIters)
    actions   = hcl.asarray(_actions)

    # Required for using true state values
    bounds     = hcl.asarray( _bounds )
    ptsEachDim = hcl.asarray( _ptsEachDim )
    sVals      = hcl.asarray( np.zeros([3]) )
    iVals      = hcl.asarray( np.zeros([3]) )

    # required for linear interpolation
    interpols  = hcl.asarray( np.zeros([8, 4]) )
    useNN      = hcl.asarray(_useNN)


    ######################################### PARALLELIZE ##########################################

    #BUG: cannot use multi-treading with interpolation
    # s_1 = solve_Vopt.Sweep_1
    # s_2 = solve_Vopt.Sweep_2
    # s_3 = solve_Vopt.Sweep_3
    # s_4 = solve_Vopt.Sweep_4
    # s_5 = solve_Vopt.Sweep_5
    # s_6 = solve_Vopt.Sweep_6
    # s_7 = solve_Vopt.Sweep_7
    # s_8 = solve_Vopt.Sweep_8

    # s[s_1].parallel(s_1.i)
    # s[s_2].parallel(s_2.i)
    # s[s_3].parallel(s_3.i)
    # s[s_4].parallel(s_4.i)
    # s[s_5].parallel(s_5.i)
    # s[s_6].parallel(s_6.i)
    # s[s_7].parallel(s_7.i)
    # s[s_8].parallel(s_8.i)

    # Use this graph and build an executable
    f = hcl.build(s, target="llvm")


    ########################################### EXECUTE ############################################

    # Now use the executable
    t_s = time.time()
    f(V_opt, actions, intermeds, trans, interpols, gamma, epsilon, iVals, sVals, bounds, ptsEachDim, count, maxIters, useNN)
    t_e = time.time()

    V = V_opt.asnumpy()
    c = count.asnumpy()

    print(V)
    print()
    print("Finished in ", int(c[0]), " iterations")
    print("Took        ", t_e-t_s, " seconds")


# Test function
value_iteration_3D()
