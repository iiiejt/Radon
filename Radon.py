#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created on Mon Aug 17 09:57:47 2020

@author: sjsty
"""

import numpy as np
import numpy.random as rnd
import matplotlib as mpl
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
import threading
import concurrent.futures
import logging
import time
import os
import csv

LRn222 = 3.8235 * 24 * 60 * 60  # the half-life for Rn-222 (in seconds)
LPo218 = 3.098 * 60  # the half-life for Po-218
LPb214 = 26.8 * 60 # the half-life for Pb-214
LBi214 = 19.9 * 60 # the half-life for Bi-214
LPo214 = 164.3e-6 # the half-life for Po-214
DC1HL = np.array([LRn222, LPo218,LPb214,LBi214,LPo214])
DC1AD = np.array([     1,      1,     0,     0,     1])
DC1Lambda = np.log(2) / DC1HL  # the decay constants for this first decay chain in units of 1/min


LRn220 = 55.6  # the half-life for Rn-220 (in seconds)
LPo216 = 0.145  # the half-life for Po-216
LPb212 = 10.64 * 60 * 60 # the half-life for Pb-212
LBi212 = 60.55 * 60 # the half-life for Bi-212
# Technically, Bi-212 can both alpha and beta decay, but the beta decay mode then alpha decays almost immediately
DC2HL = np.array([LRn220, LPo216,LPb212,LBi212])
DC2AD = np.array([     1,      1,     0,     1])
DC2Lambda = np.log(2) / DC2HL  # the decay constants for this first decay chain in units of 1/min

max_threads = len(os.sched_getaffinity(0))
thread_pool = threading.BoundedSemaphore(max_threads)


def gen_inputs(sample_time, n_samples, *rates, counts=None):
    if counts is None:
        counts = [1] * len(rates)
    proportions = [[0] * len(rates) for _ in range(n_samples)]
    for i in range(n_samples):
        for j in range(len(rates)):
            for r in range(j + 1):
                tmp = 1
                for q in range(j + 1):
                    if q != r:
                        tmp *= rates[q] / (rates[q] - rates[r])
                tmp *= np.exp(-rates[r] * i * sample_time) - np.exp(-rates[r] * (i + 1) * sample_time)
                proportions[i][j] += tmp*counts[j]
    return [sum(p) for p in proportions]


def expcount(n, sample_time, n_samples, *args, counts=None):
    if counts is None:
        counts = [1] * len(args)
    countlist = np.array([0] * n_samples)
    gen=rnd.default_rng()
    indices = [i for i, c in enumerate(counts) if c == 1]
    decays = np.cumsum(gen.exponential(args,(n,len(args))),1)
    decays = decays[:, indices]//sample_time
    for i in decays.flatten():
        if int(i) < len(countlist):
            countlist[int(i)] += 1
    return countlist

def exp_state(init_state, interval, rates, counts=None):
    if counts is None:
        counts = np.array([1] * len(init_state))
    if len(init_state) != len(rates) or len(init_state) != len(counts):
        raise Exception("Length of state, rates, and counts must match")
    count = np.array([0]*len(init_state))
    gen = rnd.default_rng()
    for type in range(len(init_state)):
        decays = gen.exponential(1/(rates[type:]),(init_state[type],len(rates)-type))
        count[type:] += np.sum(np.cumsum(decays,1)<interval,0)
    state = np.array(init_state) - count
    state[1:] += count[0:-1]
    return state, np.dot(count, counts)

def runtrial_thread(args):
    with thread_pool:
        logging.info("Thread %s: starting", args[0])
        runtrial(*(args[1:]))

def runtrial(st,tt,i,j):
    ns = tt//st
    in_rn222=gen_inputs(st,ns,*DC1Lambda)
    in_rn220=gen_inputs(st,ns,*DC2Lambda)
    rn222_est=[0]*10
    rn220_est=[0]*10
    for k in range(10):
        out=np.array(expcount(1000000,st,ns,*(1/DC1Lambda)))+np.array(expcount(1000//6,st,ns,*(1/DC2Lambda)))
        lr=LinearRegression(fit_intercept=False).fit(np.transpose(np.vstack((in_rn222,in_rn220))),out)
        rn222_est[k],rn220_est[k] = lr.coef_
    print("st: {}s, tt: {}s, Rn222 => mean: {:1.1f}, std: {:1.1f}".format(st, tt, np.mean(rn222_est),np.std(rn222_est)))
    print("st: {}s, tt: {}s, Rn220 => mean: {:1.1f}, std: {:1.1f}".format(st, tt, np.mean(rn220_est), np.std(rn220_est)))
    ratio_est = np.array(rn222_est)/np.array(rn220_est)
    print("st: {}s, tt: {}s, ratio => mean: {:1.1f}, std: {:1.1f}".format(st, tt, np.mean(ratio_est), np.std(ratio_est)))
    rn222_mean[i][j] = np.mean(rn222_est)
    rn222_stdv[i][j] = np.std(rn222_est)
    rn220_mean[i][j] = np.mean(rn220_est)
    rn220_stdv[i][j] = np.std(rn220_est)

if __name__ == "__main__":
    format = "%(asctime)s: %(message)s"
    logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")

    n_period_grid = 60
    n_period_start = 1
    n_period_step = 1
    n_time_grid = 1
    n_time_start = 1*60
    n_time_step = 1*60

    rn222_mean = [[0] * n_time_grid for _ in range(n_period_grid)]
    rn222_stdv = [[0] * n_time_grid for _ in range(n_period_grid)]
    rn220_mean = [[0] * n_time_grid for _ in range(n_period_grid)]
    rn220_stdv = [[0] * n_time_grid for _ in range(n_period_grid)]

    jobs = [(i,(i%n_period_grid)*n_period_step+n_period_step,n_time_step*(i//n_period_grid)+n_time_start,i%n_period_grid,i//n_period_grid) for i in range(n_time_grid*n_period_grid)]
    threads = list()
    for job in jobs:
        logging.info("Main\t: create and start thread %d", job[0])
        x = threading.Thread(target=runtrial_thread,args=(job,))
        threads.append(x)
        x.start()
    for t in threads:
        t.join()
    with open("rn222_mean.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rn222_mean)
    with open("rn222_std.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rn222_stdv)
    with open("rn220_mean.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rn220_mean)
    with open("rn220_std.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rn220_stdv)
