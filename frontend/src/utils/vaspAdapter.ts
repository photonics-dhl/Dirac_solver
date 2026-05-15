import { HARTREE_TO_EV } from './scanSpec';

export function adaptVaspResult(vaspData: any, config: any) {
    const eigenvalues = vaspData.eigenvalues_ev || [];
    const occupations = vaspData.occupations || [];
    let homoEV: number | undefined;
    let lumoEV: number | undefined;
    if (occupations.length > 0 && eigenvalues.length > 0) {
        for (let i = eigenvalues.length - 1; i >= 0; i--) {
            if (occupations[i] > 0.1) {
                homoEV = eigenvalues[i];
                if (i + 1 < eigenvalues.length) lumoEV = eigenvalues[i + 1];
                break;
            }
        }
    }
    const totalEnergyHa = vaspData.total_energy_ev != null
        ? vaspData.total_energy_ev / HARTREE_TO_EV
        : undefined;
    return {
        config,
        problemType: 'molecular',
        equationType: 'VASP DFT (PAW-PBE)',
        dimensionality: '3D',
        hamiltonian: [],
        eigenvalues,
        wavefunctions: [],
        probabilityDensity: [],
        verified: vaspData.status === 'success',
        computationTime: 0,
        molecular: {
            calcMode: 'gs' as const,
            moleculeName: vaspData.molecule || config.octopusMolecule || 'unknown',
            backend: 'vasp',
            energy_levels: eigenvalues,
            homo_energy: homoEV,
            lumo_energy: lumoEV,
            total_energy_hartree: totalEnergyHa,
            fermi_energy_ev: vaspData.fermi_energy_ev,
            magnetization: vaspData.magnetization,
            occupations: vaspData.occupations,
            nelect: vaspData.nelect,
            nbands: vaspData.nbands,
            scf_iterations: vaspData.scf_iterations || 0,
            converged: vaspData.status === 'success',
        },
        scheduler: {
            strategy: vaspData.execution_strategy,
        },
    };
}
