import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import ast
import pandas
import numpy

from mpl_toolkits.axes_grid1.inset_locator import zoomed_inset_axes
from mpl_toolkits.axes_grid1.inset_locator import mark_inset
from matplotlib.ticker import (MultipleLocator, FormatStrFormatter,
                               AutoMinorLocator)

if __name__ == "__main__":

    db_n_1_bh2 = pandas.read_csv('../../../results/iter_vqe_results/BeH2_iqeb_n=1_gsdqe_r=3_05-Dec-2020.csv')
    db_n_10_bh2 = pandas.read_csv('../../../results/iter_vqe_results/vip/BeH2_h_adapt_gsdqe_comp_pair_r=3_06-Oct-2020.csv')
    db_n_30_bh2 = pandas.read_csv('../../../results/iter_vqe_results/BeH2_iqeb_n=30_gsdqe_r=3_02-Dec-2020.csv')

    db_n_1_lih = pandas.read_csv('../../../results/iter_vqe_results/LiH_iqeb_n=1_gsdqe_r=3_03-Dec-2020.csv')
    db_n_10_lih = pandas.read_csv('../../../results/iter_vqe_results/vip/LiH_h_adapt_gsdqe_comp_pair_r=3_24-Sep-2020.csv')
    db_n_30_lih = pandas.read_csv('../../../results/iter_vqe_results/LiH_iqeb_n=30_gsdqe_r=3-03-Dec-2020.csv')

    df_col = 'cnot_count'

    dEs = numpy.logspace(-9, 0, 50)
    interp_bh2_1 = numpy.interp(dEs, numpy.flip(db_n_1_bh2['error'].values), numpy.flip(db_n_1_bh2[df_col].values))
    interp_bh2_10 = numpy.interp(dEs, numpy.flip(db_n_10_bh2['error'].values), numpy.flip(db_n_10_bh2[df_col].values))
    interp_bh2_30 = numpy.interp(dEs, numpy.flip(db_n_30_bh2['error'].values), numpy.flip(db_n_30_bh2[df_col].values))

    interp_lih_1 = numpy.interp(dEs, numpy.flip(db_n_1_lih['error'].values), numpy.flip(db_n_1_lih[df_col].values))
    interp_lih_10 = numpy.interp(dEs, numpy.flip(db_n_10_lih['error'].values), numpy.flip(db_n_10_lih[df_col].values))
    interp_lih_30 = numpy.interp(dEs, numpy.flip(db_n_30_lih['error'].values), numpy.flip(db_n_30_lih[df_col].values))

    fig, ax = plt.subplots()

    linewidth = 0.4
    marker = '_'

    # ax.plot(dEs, 1 - interp_bh2_10/interp_bh2_1, label=r'BeH$_2$, n=10', linewidth=linewidth, color='dodgerblue')
    # ax.plot(dEs, 1 - interp_bh2_30/interp_bh2_1, label=r'BeH$_2$, n=30', linewidth=linewidth, color='tomato')

    ax.plot(dEs, 1 - interp_lih_10 / interp_lih_1, label=r'BeH$_2$, n=10', linewidth=linewidth, color='blue')
    ax.plot(dEs, 1 - interp_lih_30 / interp_lih_1, label=r'BeH$_2$, n=30', linewidth=linewidth, color='red')

    ax.set_ylabel('Reduction of CNOTs, %')
    ax.set_xlabel(r'$E(\theta) - E_{FCI}$, Hartree')
    ax.set_xscale('log')

    ax.legend(loc=1)#, bbox_to_anchor=(1,0.4))

    plt.show()

    print('macaroni')
