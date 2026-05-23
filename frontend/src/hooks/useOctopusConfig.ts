import { useState, useEffect } from 'react';
import { Atom3D } from '../Mol3DViewer';

export type EngineMode = 'local1D' | 'octopus3D' | 'vasp';
export type CalcMode = 'gs' | 'td' | 'casida' | 'unocc' | 'opt' | 'em' | 'vib';
export type CaseType = 'boundstate_1d' | 'dft_gs_3d' | 'response_td' | 'periodic_bands' | 'hpc_scaling';

export interface OctopusConfig {
    // Engine
    engineMode: EngineMode;
    caseType: CaseType;
    // Physical constants
    unitSystem: string;
    particleMass: string;
    particleCharge: string;
    electronEnergy: string;
    // Geometry & Grid
    dimensionality: string;
    spatialRange: string;
    gridPoints: string;
    boundaryCondition: string;
    // Octopus
    octopusCalcMode: CalcMode;
    octopusDimensions: string;
    octopusSpacing: string;
    octopusRadius: string;
    octopusBoxShape: string;
    octopusMolecule: string;
    octopusTdSteps: string;
    octopusTdTimeStep: string;
    octopusPropagator: string;
    octopusEigenSolver: string;
    octopusNcpus: string;
    octopusMpiprocs: string;
    octopusExtraStates: string;
    casidaKohnShamStates: string;
    // VASP
    vaspEncuit: string;
    vaspEdiff: string;
    vaspNelmin: string;
    vaspIsmear: string;
    vaspSigma: string;
    vaspNelect: string;
    vaspNbands: string;
    vaspKpointsType: string;
    vaspBox: string;
    vaspPrec: string;
    // GS
    gsConvergenceProfile: string;
    gsEnableScan: boolean;
    gsScanSpec: string;
    gsReferenceSpacing: string;
    gsReferenceUrl: string;
    // TD
    tdExcitationType: string;
    tdPolarization: string;
    tdFieldAmplitude: string;
    tdGaussianSigma: string;
    tdGaussianT0: string;
    tdSinFrequency: string;
    // Free electron probe
    feProbeEnabled: boolean;
    feProbeVelocity: string;
    feProbeDirection: string;
    feProbeCx: string;
    feProbeCy: string;
    feProbeCz: string;
    feProbeBeamCount: string;
    feProbeCharge: string;
    // DFT
    mixingScheme: string;
    spinComponents: string;
    xcCategory: string;
    xcPreset: string;
    xcOverride: string;
    speciesMode: string;
    pseudopotentialSet: string;
    // Periodic
    periodicDimensions: string;
    kpointsGrid: string;
    latticeA: string;
    latticeB: string;
    latticeC: string;
    // Advanced grid
    derivativesOrder: string;
    curvMethod: string;
    curvGygiAlpha: string;
    doubleGrid: boolean;
    // Potential (local 1D)
    potentialType: string;
    potentialStrength: string;
    wellWidth: string;
    customExpression: string;
    potentialDataMode: string;
    // Equation
    equationType: string;
    problemType: string;
    picture: string;
    // Time evolution
    numTimeSteps: string;
    totalTime: string;
    gaussianCenter: string;
    gaussianWidth: string;
    gaussianMomentum: string;
    // Scattering
    scatteringEMin: string;
    scatteringEMax: string;
    scatteringESteps: string;
    // Geometry mode
    geomMode: 'preset' | 'custom';
    customAtoms: Atom3D[];
    confirmedAtoms: Atom3D[] | null;
    confirmedLabel: string;
    showGeomPreview: boolean;
}

export interface OctopusConfigSetters {
    setUnitSystem: (v: string) => void;
    setParticleMass: (v: string) => void;
    setParticleCharge: (v: string) => void;
    setElectronEnergy: (v: string) => void;
    setDimensionality: (v: string) => void;
    setSpatialRange: (v: string) => void;
    setGridPoints: (v: string) => void;
    setBoundaryCondition: (v: string) => void;
    setEngineMode: (v: EngineMode) => void;
    setCaseType: (v: CaseType) => void;
    setOctopusCalcMode: (v: CalcMode) => void;
    setOctopusDimensions: (v: string) => void;
    setOctopusSpacing: (v: string) => void;
    setOctopusRadius: (v: string) => void;
    setOctopusBoxShape: (v: string) => void;
    setOctopusMolecule: (v: string) => void;
    setOctopusTdSteps: (v: string) => void;
    setOctopusTdTimeStep: (v: string) => void;
    setOctopusPropagator: (v: string) => void;
    setOctopusEigenSolver: (v: string) => void;
    setOctopusNcpus: (v: string) => void;
    setOctopusMpiprocs: (v: string) => void;
    setOctopusExtraStates: (v: string) => void;
    setCasidaKohnShamStates: (v: string) => void;
    setVaspEncuit: (v: string) => void;
    setVaspEdiff: (v: string) => void;
    setVaspNelmin: (v: string) => void;
    setVaspIsmear: (v: string) => void;
    setVaspSigma: (v: string) => void;
    setVaspNelect: (v: string) => void;
    setVaspNbands: (v: string) => void;
    setVaspKpointsType: (v: string) => void;
    setVaspBox: (v: string) => void;
    setVaspPrec: (v: string) => void;
    setGsConvergenceProfile: (v: string) => void;
    setGsEnableScan: (v: boolean) => void;
    setGsScanSpec: (v: string) => void;
    setGsReferenceSpacing: (v: string) => void;
    setGsReferenceUrl: (v: string) => void;
    setTdExcitationType: (v: string) => void;
    setTdPolarization: (v: string) => void;
    setTdFieldAmplitude: (v: string) => void;
    setTdGaussianSigma: (v: string) => void;
    setTdGaussianT0: (v: string) => void;
    setTdSinFrequency: (v: string) => void;
    setFeProbeEnabled: (v: boolean) => void;
    setFeProbeVelocity: (v: string) => void;
    setFeProbeDirection: (v: string) => void;
    setFeProbeCx: (v: string) => void;
    setFeProbeCy: (v: string) => void;
    setFeProbeCz: (v: string) => void;
    setFeProbeBeamCount: (v: string) => void;
    setFeProbeCharge: (v: string) => void;
    setMixingScheme: (v: string) => void;
    setSpinComponents: (v: string) => void;
    setXcCategory: (v: string) => void;
    setXcPreset: (v: string) => void;
    setXcOverride: (v: string) => void;
    setSpeciesMode: (v: string) => void;
    setPseudopotentialSet: (v: string) => void;
    setPeriodicDimensions: (v: string) => void;
    setKpointsGrid: (v: string) => void;
    setLatticeA: (v: string) => void;
    setLatticeB: (v: string) => void;
    setLatticeC: (v: string) => void;
    setDerivativesOrder: (v: string) => void;
    setCurvMethod: (v: string) => void;
    setCurvGygiAlpha: (v: string) => void;
    setDoubleGrid: (v: boolean) => void;
    setPotentialType: (v: string) => void;
    setPotentialStrength: (v: string) => void;
    setWellWidth: (v: string) => void;
    setCustomExpression: (v: string) => void;
    setPotentialDataMode: (v: string) => void;
    setEquationType: (v: string) => void;
    setProblemType: (v: string) => void;
    setPicture: (v: string) => void;
    setNumTimeSteps: (v: string) => void;
    setTotalTime: (v: string) => void;
    setGaussianCenter: (v: string) => void;
    setGaussianWidth: (v: string) => void;
    setGaussianMomentum: (v: string) => void;
    setScatteringEMin: (v: string) => void;
    setScatteringEMax: (v: string) => void;
    setScatteringESteps: (v: string) => void;
    setGeomMode: (v: 'preset' | 'custom') => void;
    setCustomAtoms: (v: Atom3D[]) => void;
    setConfirmedAtoms: (v: Atom3D[] | null) => void;
    setConfirmedLabel: (v: string) => void;
    setShowGeomPreview: (v: boolean) => void;
}

export function useOctopusConfig(): { config: OctopusConfig; setters: OctopusConfigSetters } {
    const [unitSystem, setUnitSystem] = useState('natural');
    const [particleMass, setParticleMass] = useState('0.511');
    const [particleCharge, setParticleCharge] = useState('-1');
    const [electronEnergy, setElectronEnergy] = useState('1.0');
    const [dimensionality, setDimensionality] = useState('1D');
    const [spatialRange, setSpatialRange] = useState('10.0');
    const [gridPoints, setGridPoints] = useState('100');
    const [boundaryCondition, setBoundaryCondition] = useState('dirichlet');
    const [engineMode, setEngineMode] = useState<EngineMode>('octopus3D');
    const [caseType, setCaseType] = useState<CaseType>('dft_gs_3d');
    const [octopusCalcMode, setOctopusCalcMode] = useState<CalcMode>('gs');
    const [octopusDimensions, setOctopusDimensions] = useState('3D');
    const [octopusSpacing, setOctopusSpacing] = useState('0.4');
    const [octopusRadius, setOctopusRadius] = useState('4.0');
    const [octopusBoxShape, setOctopusBoxShape] = useState('sphere');
    const [octopusMolecule, setOctopusMolecule] = useState('H2O');
    const [octopusTdSteps, setOctopusTdSteps] = useState('5000');
    const [octopusTdTimeStep, setOctopusTdTimeStep] = useState('0.05');
    const [octopusPropagator, setOctopusPropagator] = useState('aetrs');
    const [octopusEigenSolver, setOctopusEigenSolver] = useState('');
    const [octopusNcpus, setOctopusNcpus] = useState('64');
    const [octopusMpiprocs, setOctopusMpiprocs] = useState('64');
    const [vaspEncuit, setVaspEncuit] = useState('400');
    const [vaspEdiff, setVaspEdiff] = useState('1e-6');
    const [vaspNelmin, setVaspNelmin] = useState('5');
    const [vaspIsmear, setVaspIsmear] = useState('0');
    const [vaspSigma, setVaspSigma] = useState('0.01');
    const [vaspNelect, setVaspNelect] = useState('');
    const [vaspNbands, setVaspNbands] = useState('');
    const [vaspKpointsType, setVaspKpointsType] = useState('gamma');
    const [vaspBox, setVaspBox] = useState('10.0');
    const [vaspPrec, setVaspPrec] = useState('Normal');
    const [gsConvergenceProfile, setGsConvergenceProfile] = useState('general');
    const [gsEnableScan, setGsEnableScan] = useState(false);
    const [gsScanSpec, setGsScanSpec] = useState('0.26,0.24,0.22,0.20,0.18,0.16,0.14');
    const [gsReferenceSpacing, setGsReferenceSpacing] = useState('0.16');
    const [gsReferenceUrl, setGsReferenceUrl] = useState('https://www.octopus-code.org/documentation/16/tutorial/basics/total_energy_convergence/');
    const [tdExcitationType, setTdExcitationType] = useState('delta');
    const [tdPolarization, setTdPolarization] = useState('1');
    const [tdFieldAmplitude, setTdFieldAmplitude] = useState('0.01');
    const [tdGaussianSigma, setTdGaussianSigma] = useState('5.0');
    const [tdGaussianT0, setTdGaussianT0] = useState('10.0');
    const [tdSinFrequency, setTdSinFrequency] = useState('0.057');
    const [feProbeEnabled, setFeProbeEnabled] = useState<boolean>(false);
    const [feProbeVelocity, setFeProbeVelocity] = useState('0.5');
    const [feProbeDirection, setFeProbeDirection] = useState<'x' | 'y' | 'z'>('x');
    const [feProbeCx, setFeProbeCx] = useState('0.0');
    const [feProbeCy, setFeProbeCy] = useState('2.0');
    const [feProbeCz, setFeProbeCz] = useState('0.0');
    const [feProbeBeamCount, setFeProbeBeamCount] = useState('1');
    const [feProbeCharge, setFeProbeCharge] = useState('-1');
    const [octopusExtraStates, setOctopusExtraStates] = useState('4');
    const [casidaKohnShamStates, setCasidaKohnShamStates] = useState('1-8');
    const [mixingScheme, setMixingScheme] = useState('broyden');
    const [spinComponents, setSpinComponents] = useState('unpolarized');
    const [xcCategory, setXcCategory] = useState('lda');
    const [xcPreset, setXcPreset] = useState('lda_x+lda_c_pz');
    const [xcOverride, setXcOverride] = useState('');
    const [speciesMode, setSpeciesMode] = useState('pseudo');
    const [pseudopotentialSet, setPseudopotentialSet] = useState('standard');
    const [periodicDimensions, setPeriodicDimensions] = useState<'0' | '1' | '2' | '3'>('0');
    const [kpointsGrid, setKpointsGrid] = useState('2 2 2');
    const [latticeA, setLatticeA] = useState('10.263');
    const [latticeB, setLatticeB] = useState('10.263');
    const [latticeC, setLatticeC] = useState('10.263');
    const [derivativesOrder, setDerivativesOrder] = useState<'4' | '6' | '8'>('4');
    const [curvMethod, setCurvMethod] = useState<'uniform' | 'gygi'>('uniform');
    const [curvGygiAlpha, setCurvGygiAlpha] = useState('2.0');
    const [doubleGrid, setDoubleGrid] = useState<boolean>(false);
    const [showGeomPreview, setShowGeomPreview] = useState<boolean>(false);
    const [geomMode, setGeomMode] = useState<'preset' | 'custom'>('preset');
    const [customAtoms, setCustomAtoms] = useState<Atom3D[]>([]);
    const [confirmedAtoms, setConfirmedAtoms] = useState<Atom3D[] | null>(null);
    const [confirmedLabel, setConfirmedLabel] = useState<string>('');
    const [potentialType, setPotentialType] = useState('InfiniteWell');
    const [potentialStrength, setPotentialStrength] = useState('-1.0');
    const [wellWidth, setWellWidth] = useState('1.0');
    const [customExpression, setCustomExpression] = useState('');
    const [potentialDataMode, setPotentialDataMode] = useState<'analytical' | 'data'>('analytical');
    const [equationType, setEquationType] = useState('Schrodinger');
    const [problemType, setProblemType] = useState('boundstate');
    const [picture, setPicture] = useState('auto');
    const [numTimeSteps, setNumTimeSteps] = useState('50');
    const [totalTime, setTotalTime] = useState('5.0');
    const [gaussianCenter, setGaussianCenter] = useState('0.0');
    const [gaussianWidth, setGaussianWidth] = useState('0.05');
    const [gaussianMomentum, setGaussianMomentum] = useState('5.0');
    const [scatteringEMin, setScatteringEMin] = useState('0.0');
    const [scatteringEMax, setScatteringEMax] = useState('20.0');
    const [scatteringESteps, setScatteringESteps] = useState('200');

    useEffect(() => {
        if (octopusCalcMode === 'td' || octopusCalcMode === 'casida') {
            setCaseType('response_td');
        } else if (octopusCalcMode === 'em' || octopusCalcMode === 'vib') {
            setCaseType('periodic_bands');
        } else {
            setCaseType('dft_gs_3d');
        }
    }, [octopusCalcMode]);

    useEffect(() => {
        const mol = (octopusMolecule || '').trim();
        if (mol === 'N_atom') {
            setGsConvergenceProfile('n_atom_official');
        } else if (mol === 'CH4') {
            setGsConvergenceProfile('ch4_tutorial');
        } else {
            setGsConvergenceProfile('general');
        }
    }, [octopusMolecule]);

    const config: OctopusConfig = {
        unitSystem, particleMass, particleCharge, electronEnergy,
        dimensionality, spatialRange, gridPoints, boundaryCondition,
        engineMode, caseType,
        octopusCalcMode, octopusDimensions, octopusSpacing, octopusRadius,
        octopusBoxShape, octopusMolecule, octopusTdSteps, octopusTdTimeStep,
        octopusPropagator, octopusEigenSolver, octopusNcpus, octopusMpiprocs,
        octopusExtraStates,
        casidaKohnShamStates,
        vaspEncuit, vaspEdiff, vaspNelmin, vaspIsmear, vaspSigma,
        vaspNelect, vaspNbands, vaspKpointsType, vaspBox, vaspPrec,
        gsConvergenceProfile, gsEnableScan, gsScanSpec, gsReferenceSpacing, gsReferenceUrl,
        tdExcitationType, tdPolarization, tdFieldAmplitude,
        tdGaussianSigma, tdGaussianT0, tdSinFrequency,
        feProbeEnabled, feProbeVelocity, feProbeDirection,
        feProbeCx, feProbeCy, feProbeCz, feProbeBeamCount, feProbeCharge,
        mixingScheme, spinComponents,
        xcCategory, xcPreset, xcOverride,
        speciesMode, pseudopotentialSet,
        periodicDimensions, kpointsGrid, latticeA, latticeB, latticeC,
        derivativesOrder, curvMethod, curvGygiAlpha, doubleGrid,
        potentialType, potentialStrength, wellWidth, customExpression, potentialDataMode,
        equationType, problemType, picture,
        numTimeSteps, totalTime, gaussianCenter, gaussianWidth, gaussianMomentum,
        scatteringEMin, scatteringEMax, scatteringESteps,
        geomMode, customAtoms, confirmedAtoms, confirmedLabel, showGeomPreview,
    };

    const setters: OctopusConfigSetters = {
        setUnitSystem, setParticleMass, setParticleCharge, setElectronEnergy,
        setDimensionality, setSpatialRange, setGridPoints, setBoundaryCondition,
        setEngineMode, setCaseType,
        setOctopusCalcMode, setOctopusDimensions, setOctopusSpacing, setOctopusRadius,
        setOctopusBoxShape, setOctopusMolecule, setOctopusTdSteps, setOctopusTdTimeStep,
        setOctopusPropagator, setOctopusEigenSolver, setOctopusNcpus, setOctopusMpiprocs,
        setOctopusExtraStates,
        setCasidaKohnShamStates,
        setVaspEncuit, setVaspEdiff, setVaspNelmin, setVaspIsmear, setVaspSigma,
        setVaspNelect, setVaspNbands, setVaspKpointsType, setVaspBox, setVaspPrec,
        setGsConvergenceProfile, setGsEnableScan, setGsScanSpec, setGsReferenceSpacing, setGsReferenceUrl,
        setTdExcitationType, setTdPolarization, setTdFieldAmplitude,
        setTdGaussianSigma, setTdGaussianT0, setTdSinFrequency,
        setFeProbeEnabled, setFeProbeVelocity, setFeProbeDirection: setFeProbeDirection as (v: string) => void,
        setFeProbeCx, setFeProbeCy, setFeProbeCz, setFeProbeBeamCount, setFeProbeCharge,
        setMixingScheme, setSpinComponents,
        setXcCategory, setXcPreset, setXcOverride,
        setSpeciesMode, setPseudopotentialSet,
        setPeriodicDimensions: setPeriodicDimensions as (v: string) => void,
        setKpointsGrid, setLatticeA, setLatticeB, setLatticeC,
        setDerivativesOrder: setDerivativesOrder as (v: string) => void,
        setCurvMethod: setCurvMethod as (v: string) => void,
        setCurvGygiAlpha, setDoubleGrid,
        setPotentialType, setPotentialStrength, setWellWidth, setCustomExpression, setPotentialDataMode: setPotentialDataMode as (v: string) => void,
        setEquationType, setProblemType, setPicture,
        setNumTimeSteps, setTotalTime, setGaussianCenter, setGaussianWidth, setGaussianMomentum,
        setScatteringEMin, setScatteringEMax, setScatteringESteps,
        setGeomMode, setCustomAtoms, setConfirmedAtoms, setConfirmedLabel, setShowGeomPreview,
    };

    return { config, setters };
}
