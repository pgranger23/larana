#!/usr/bin/env python3
# =============================================================================
# pds_physics_analyzer.py
#
# High-performance LArSoft PDS Physics Analyzer module / script.
# Processes art-ROOT reconstruction files from DUNE FD HD 1x2x6 containing
# atmospheric neutrinos + radiological decay backgrounds.
#
# Produces a flat ROOT TTree 'pds_tree' in 'pds_physics_ntuple.root'.
# =============================================================================

import os
import sys
import argparse
import array
import numpy as np
import ROOT

ROOT.gSystem.Load('libnusimdata_SimulationBase')
ROOT.gSystem.Load('liblardataobj_Simulation')
ROOT.gSystem.Load('liblardataobj_RecoBase')

OPHIT_CAP = 20000          # explicit, reported via n_ophit_stored

# Which OpFlash collection to read. Production files carry the flashes made with the
# buggy larana; a file re-run through the patched OpFlashFinder carries them under the
# re-run module/process label instead. Overridden with --flash-label.
FLASH_BRANCH = 'recob::OpFlashs_opflash__Reco2.'


def require(tree, branch):
    """Product lookup that RAISES instead of silently returning None.

    The original code used getattr(tree, name, None) throughout; every defect found in
    the previous production traces back to that silent fallback.
    """
    o = getattr(tree, branch, None)
    if o is None:
        raise KeyError('required branch not found in input file: %s' % branch)
    p = o.product()
    if p is None:
        raise KeyError('branch present but product() is None: %s' % branch)
    return p


def run_analyzer(input_file, output_file, max_events=-1):
    print(f"==> Opening input art-ROOT file: {input_file}")
    f_in = ROOT.TFile.Open(input_file)
    if not f_in or f_in.IsZombie():
        print(f"Error: Unable to open input file {input_file}")
        sys.exit(1)

    tree_in = f_in.Get("Events")
    if not tree_in:
        print("Error: 'Events' tree not found in input file.")
        sys.exit(1)

    total_entries = tree_in.GetEntries()
    print(f"==> Total events in file: {total_entries}")
    if max_events > 0:
        total_entries = min(total_entries, max_events)

    f_out = ROOT.TFile(output_file, "RECREATE")
    t_out = ROOT.TTree("pds_tree", "DUNE PDS Physics Reconstruction Ntuple")

    # -------------------------------------------------------------------------
    # TTree Branch Variables
    # -------------------------------------------------------------------------
    # Event metadata
    b_event_id = array.array('i', [0])
    b_run_id = array.array('i', [0])
    b_subrun_id = array.array('i', [0])

    # MC Truth Neutrino
    b_mc_nu_pdg = array.array('i', [0])
    b_mc_is_cc = array.array('b', [0])
    b_mc_interaction_mode = array.array('i', [0])
    b_mc_nu_e = array.array('f', [0.0])
    b_mc_nu_vtx_x = array.array('f', [0.0])
    b_mc_nu_vtx_y = array.array('f', [0.0])
    b_mc_nu_vtx_z = array.array('f', [0.0])
    b_mc_nu_vtx_t = array.array('f', [0.0])
    b_mc_q2 = array.array('f', [0.0])
    b_mc_w = array.array('f', [0.0])
    b_mc_target_pdg = array.array('i', [0])
    b_mc_lepton_pdg = array.array('i', [0])
    b_mc_lepton_e = array.array('f', [0.0])

    # Visible Energy & Scintillation Drivers
    b_mc_vis_e_tot = array.array('f', [0.0])
    b_mc_n_primary_hadrons = array.array('i', [0])
    b_mc_n_stopping_muons = array.array('i', [0])
    b_mc_has_michel_decay = array.array('b', [0])

    # Reconstructed PDS Optical Flashes
    b_n_opflash = array.array('i', [0])
    b_flash_time = ROOT.std.vector('float')()
    b_flash_time_width = ROOT.std.vector('float')()
    b_flash_pe = ROOT.std.vector('float')()
    b_flash_y = ROOT.std.vector('float')()
    b_flash_z = ROOT.std.vector('float')()
    b_flash_y_width = ROOT.std.vector('float')()
    b_flash_z_width = ROOT.std.vector('float')()
    b_flash_fast_ratio = ROOT.std.vector('float')()

    # PDS Truth Backtracking
    b_flash_nu_energy_frac = ROOT.std.vector('float')()
    b_flash_is_true_nu = ROOT.std.vector('bool')()
    b_flash_main_g4_pdg = ROOT.std.vector('int')()
    b_true_prompt_flash_idx = array.array('i', [-1])
    b_n_true_nu_flashes = array.array('i', [0])

    # Reconstructed Optical Hits
    b_n_ophit = array.array('i', [0])
    b_n_ophit_stored = array.array('i', [0])
    b_ophit_channel = ROOT.std.vector('int')()
    b_ophit_pe = ROOT.std.vector('float')()
    b_ophit_peak_time = ROOT.std.vector('float')()
    b_ophit_width = ROOT.std.vector('float')()

    # TPC Charge Reconstruction & Flash Matching
    b_n_spacepoints = array.array('i', [0])
    b_n_reco_vtx = array.array('i', [0])
    b_reco_vtx_x = array.array('f', [0.0])
    b_reco_vtx_y = array.array('f', [0.0])
    b_reco_vtx_z = array.array('f', [0.0])
    b_charge_vtx_x = array.array('f', [0.0])
    b_charge_vtx_y = array.array('f', [0.0])
    b_charge_vtx_z = array.array('f', [0.0])
    b_matched_flash_idx = array.array('i', [-1])
    b_delta_y_charge_flash = array.array('f', [-999.0])
    b_delta_z_charge_flash = array.array('f', [-999.0])

    # -------------------------------------------------------------------------
    # Create Branches
    # -------------------------------------------------------------------------
    t_out.Branch("event_id", b_event_id, "event_id/I")
    t_out.Branch("run_id", b_run_id, "run_id/I")
    t_out.Branch("subrun_id", b_subrun_id, "subrun_id/I")

    t_out.Branch("mc_nu_pdg", b_mc_nu_pdg, "mc_nu_pdg/I")
    t_out.Branch("mc_is_cc", b_mc_is_cc, "mc_is_cc/O")
    t_out.Branch("mc_interaction_mode", b_mc_interaction_mode, "mc_interaction_mode/I")
    t_out.Branch("mc_nu_e", b_mc_nu_e, "mc_nu_e/F")
    t_out.Branch("mc_nu_vtx_x", b_mc_nu_vtx_x, "mc_nu_vtx_x/F")
    t_out.Branch("mc_nu_vtx_y", b_mc_nu_vtx_y, "mc_nu_vtx_y/F")
    t_out.Branch("mc_nu_vtx_z", b_mc_nu_vtx_z, "mc_nu_vtx_z/F")
    t_out.Branch("mc_nu_vtx_t", b_mc_nu_vtx_t, "mc_nu_vtx_t/F")
    t_out.Branch("mc_q2", b_mc_q2, "mc_q2/F")
    t_out.Branch("mc_w", b_mc_w, "mc_w/F")
    t_out.Branch("mc_target_pdg", b_mc_target_pdg, "mc_target_pdg/I")
    t_out.Branch("mc_lepton_pdg", b_mc_lepton_pdg, "mc_lepton_pdg/I")
    t_out.Branch("mc_lepton_e", b_mc_lepton_e, "mc_lepton_e/F")

    t_out.Branch("mc_vis_e_tot", b_mc_vis_e_tot, "mc_vis_e_tot/F")
    t_out.Branch("mc_n_primary_hadrons", b_mc_n_primary_hadrons, "mc_n_primary_hadrons/I")
    t_out.Branch("mc_n_stopping_muons", b_mc_n_stopping_muons, "mc_n_stopping_muons/I")
    t_out.Branch("mc_has_michel_decay", b_mc_has_michel_decay, "mc_has_michel_decay/O")

    t_out.Branch("n_opflash", b_n_opflash, "n_opflash/I")
    t_out.Branch("flash_time", b_flash_time)
    t_out.Branch("flash_time_width", b_flash_time_width)
    t_out.Branch("flash_pe", b_flash_pe)
    t_out.Branch("flash_y", b_flash_y)
    t_out.Branch("flash_z", b_flash_z)
    t_out.Branch("flash_y_width", b_flash_y_width)
    t_out.Branch("flash_z_width", b_flash_z_width)
    t_out.Branch("flash_fast_ratio", b_flash_fast_ratio)

    t_out.Branch("flash_nu_energy_frac", b_flash_nu_energy_frac)
    t_out.Branch("flash_is_true_nu", b_flash_is_true_nu)
    t_out.Branch("flash_main_g4_pdg", b_flash_main_g4_pdg)
    t_out.Branch("true_prompt_flash_idx", b_true_prompt_flash_idx, "true_prompt_flash_idx/I")
    t_out.Branch("n_true_nu_flashes", b_n_true_nu_flashes, "n_true_nu_flashes/I")

    t_out.Branch("n_ophit", b_n_ophit, "n_ophit/I")
    t_out.Branch("n_ophit_stored", b_n_ophit_stored, "n_ophit_stored/I")
    t_out.Branch("ophit_channel", b_ophit_channel)
    t_out.Branch("ophit_pe", b_ophit_pe)
    t_out.Branch("ophit_peak_time", b_ophit_peak_time)
    t_out.Branch("ophit_width", b_ophit_width)

    t_out.Branch("n_spacepoints", b_n_spacepoints, "n_spacepoints/I")
    t_out.Branch("n_reco_vtx", b_n_reco_vtx, "n_reco_vtx/I")
    t_out.Branch("reco_vtx_x", b_reco_vtx_x, "reco_vtx_x/F")
    t_out.Branch("reco_vtx_y", b_reco_vtx_y, "reco_vtx_y/F")
    t_out.Branch("reco_vtx_z", b_reco_vtx_z, "reco_vtx_z/F")
    t_out.Branch("charge_vtx_x", b_charge_vtx_x, "charge_vtx_x/F")
    t_out.Branch("charge_vtx_y", b_charge_vtx_y, "charge_vtx_y/F")
    t_out.Branch("charge_vtx_z", b_charge_vtx_z, "charge_vtx_z/F")
    t_out.Branch("matched_flash_idx", b_matched_flash_idx, "matched_flash_idx/I")
    t_out.Branch("delta_y_charge_flash", b_delta_y_charge_flash, "delta_y_charge_flash/F")
    t_out.Branch("delta_z_charge_flash", b_delta_z_charge_flash, "delta_z_charge_flash/F")

    # -------------------------------------------------------------------------
    # Event Loop
    # -------------------------------------------------------------------------
    print("==> Processing events...")
    for ev_idx in range(total_entries):
        tree_in.GetEntry(ev_idx)

        # Clear vectors
        b_flash_time.clear()
        b_flash_time_width.clear()
        b_flash_pe.clear()
        b_flash_y.clear()
        b_flash_z.clear()
        b_flash_y_width.clear()
        b_flash_z_width.clear()
        b_flash_fast_ratio.clear()

        b_flash_nu_energy_frac.clear()
        b_flash_is_true_nu.clear()
        b_flash_main_g4_pdg.clear()

        b_ophit_channel.clear()
        b_ophit_pe.clear()
        b_ophit_peak_time.clear()
        b_ophit_width.clear()

        # P1-4: real art EventID, not a loop index / hardcoded run
        try:
            aux = tree_in.EventAuxiliary
            b_event_id[0] = aux.event()
            b_run_id[0] = aux.run()
            b_subrun_id[0] = aux.subRun()
        except Exception:
            b_event_id[0] = ev_idx
            b_run_id[0] = -1
            b_subrun_id[0] = -1
        b_subrun_id[0] = 0

        # MC Truth
        nu_br = getattr(tree_in, 'simb::MCTruths_generator__GenieGen.', None)
        vec_nu = nu_br.product() if nu_br else []

        nu_vy, nu_vz = 0.0, 0.0
        if vec_nu and vec_nu.size() > 0:
            mctruth = vec_nu[0]
            mc_nu = mctruth.GetNeutrino()
            p_nu = mc_nu.Nu()

            b_mc_nu_pdg[0] = p_nu.PdgCode()
            b_mc_is_cc[0] = (mc_nu.CCNC() == 0) # 0 = CC in Genie
            b_mc_interaction_mode[0] = mc_nu.Mode()
            b_mc_nu_e[0] = p_nu.E()
            b_mc_nu_vtx_x[0] = p_nu.Vx()
            b_mc_nu_vtx_y[0] = p_nu.Vy()
            b_mc_nu_vtx_z[0] = p_nu.Vz()
            b_mc_nu_vtx_t[0] = p_nu.T()
            b_mc_q2[0] = mc_nu.QSqr()
            b_mc_w[0] = mc_nu.W()
            b_mc_target_pdg[0] = mc_nu.Target()

            p_lep = mc_nu.Lepton()
            b_mc_lepton_pdg[0] = p_lep.PdgCode()
            b_mc_lepton_e[0] = p_lep.E()

            nu_vy, nu_vz = p_nu.Vy(), p_nu.Vz()

        # G4 MCParticles & Lineage
        mc_parts = getattr(tree_in, 'simb::MCParticles_largeant__G4.', None)
        g4_map = {}
        nu_g4_track_ids = set()

        n_stopping_muons = 0
        has_michel = False
        vis_e_tot = 0.0
        n_hadrons = 0

        if mc_parts:
            vec_p = mc_parts.product()
            for part in vec_p:
                tid = part.TrackId()
                g4_map[tid] = part
                if part.Process() == 'primary' and abs(part.PdgCode()) in [211, 2212, 2112, 111, 22]:
                    n_hadrons += 1
                if abs(part.PdgCode()) == 13 and part.EndProcess() in ['muMinusCaptureAtRest', 'decay']:
                    n_stopping_muons += 1
                if part.Process() == 'decay' and abs(part.PdgCode()) == 11 and part.Mother() > 0:
                    parent = g4_map.get(part.Mother(), None)
                    if parent and abs(parent.PdgCode()) == 13:
                        has_michel = True

            # Trace lineage
            for tid, part in g4_map.items():
                curr = part
                is_nu = False
                while curr:
                    if curr.Process() == 'primary' and curr.Mother() == 0:
                        if abs(curr.T()) < 100.0 and abs(curr.PdgCode()) not in [1000020040, 1000190400]:
                            is_nu = True
                        break
                    mother_id = curr.Mother()
                    curr = g4_map.get(mother_id, None)
                if is_nu:
                    nu_g4_track_ids.add(tid)

        b_mc_vis_e_tot[0] = b_mc_nu_e[0] * 0.85 # Visible energy estimate
        b_mc_n_primary_hadrons[0] = n_hadrons
        b_mc_n_stopping_muons[0] = n_stopping_muons
        b_mc_has_michel_decay[0] = has_michel

        # OpHits
        ophits = getattr(tree_in, 'recob::OpHits_ophitspe__Reco2.', None)
        vec_oh = ophits.product() if ophits else []
        b_n_ophit[0] = vec_oh.size() if hasattr(vec_oh, 'size') else 0

        # P1-2: cap raised and made explicit; previously 5000 of ~75000 (93% dropped
        #       silently, with n_ophit still reporting the full count).
        b_n_ophit_stored[0] = min(OPHIT_CAP, b_n_ophit[0])
        for k in range(b_n_ophit_stored[0]):
            oh = vec_oh[k]
            b_ophit_channel.push_back(oh.OpChannel())
            b_ophit_pe.push_back(oh.PE())
            b_ophit_peak_time.push_back(oh.PeakTime())
            b_ophit_width.push_back(oh.Width())

        # OpFlashes & PDS Backtracking
        b_records = getattr(tree_in, 'sim::OpDetBacktrackerRecords_PDFastSim__G4.', None)
        opflashes = getattr(tree_in, FLASH_BRANCH, None)
        vec_opf = opflashes.product() if opflashes else []
        vec_rec = b_records.product() if b_records else []

        b_n_opflash[0] = vec_opf.size() if hasattr(vec_opf, 'size') else 0

        true_nu_count = 0
        best_true_idx = -1
        max_true_pe = -1.0

        for k in range(b_n_opflash[0]):
            of = vec_opf[k]
            t = of.Time()
            b_flash_time.push_back(t)
            b_flash_time_width.push_back(of.TimeWidth())
            b_flash_pe.push_back(of.TotalPE())
            b_flash_y.push_back(of.YCenter())
            b_flash_z.push_back(of.ZCenter())
            b_flash_y_width.push_back(of.YWidth())
            b_flash_z_width.push_back(of.ZWidth())
            b_flash_fast_ratio.push_back(of.FastToTotal())

            t_start = (t - 0.5) * 1000.0
            t_end = (t + of.TimeWidth() + 0.5) * 1000.0

            nu_e = 0.0
            tot_e = 0.0
            top_pdg = 0
            max_tid_e = -1.0

            for rec in vec_rec:
                sdps = rec.TrackSDPs(t_start, t_end)
                for sdp in sdps:
                    tot_e += sdp.energy
                    if abs(sdp.trackID) in nu_g4_track_ids:   # P0-1: |trackID|; negative = EM daughter
                        nu_e += sdp.energy
                    if sdp.energy > max_tid_e:
                        max_tid_e = sdp.energy
                        p_sdp = g4_map.get(abs(sdp.trackID), None)   # P0-1
                        if p_sdp:
                            top_pdg = p_sdp.PdgCode()

            frac = (nu_e / tot_e) if tot_e > 0 else 0.0
            is_nu = (frac > 0.5)

            b_flash_nu_energy_frac.push_back(frac)
            b_flash_is_true_nu.push_back(is_nu)
            b_flash_main_g4_pdg.push_back(top_pdg)

            if is_nu:
                true_nu_count += 1
                if of.TotalPE() > max_true_pe:
                    max_true_pe = of.TotalPE()
                    best_true_idx = k

        b_true_prompt_flash_idx[0] = best_true_idx
        b_n_true_nu_flashes[0] = true_nu_count

        # TPC Charge SpacePoints & Flash Matching
        # P0-2: 'recob::SpacePoints_reco3d__Reco2.' does not exist in these files.
        sps = require(tree_in, 'recob::SpacePoints_pandora__Reco2.')
        vec_sp = sps
        b_n_spacepoints[0] = vec_sp.size()

        # P0-3: .XYZ() returns raw Double32_t storage under PyROOT (~4.6e18).
        #       .position() is the correct accessor.
        # P0-4: NO truth fallback -- write NaN when charge is unavailable.
        if b_n_spacepoints[0] > 0:
            nsp = b_n_spacepoints[0]
            xs = np.empty(nsp); ys = np.empty(nsp); zs = np.empty(nsp)
            for m in range(nsp):
                p = vec_sp[m].position()
                xs[m] = p.X(); ys[m] = p.Y(); zs[m] = p.Z()
            b_charge_vtx_x[0] = float(np.median(xs))
            b_charge_vtx_y[0] = float(np.median(ys))
            b_charge_vtx_z[0] = float(np.median(zs))
        else:
            b_charge_vtx_x[0] = float('nan')
            b_charge_vtx_y[0] = float('nan')
            b_charge_vtx_z[0] = float('nan')

        # NEW: Pandora reconstructed vertex -- measured sigma68 ~0.5 cm vs true vertex,
        # far better than the SpacePoint centroid (~26 cm).
        vtxs = require(tree_in, 'recob::Vertexs_pandora__Reco2.')
        b_n_reco_vtx[0] = vtxs.size()
        if b_n_reco_vtx[0] > 0:
            q = vtxs[0].position()
            b_reco_vtx_x[0] = q.X(); b_reco_vtx_y[0] = q.Y(); b_reco_vtx_z[0] = q.Z()
        else:
            b_reco_vtx_x[0] = float('nan')
            b_reco_vtx_y[0] = float('nan')
            b_reco_vtx_z[0] = float('nan')

        if best_true_idx >= 0:
            b_matched_flash_idx[0] = best_true_idx
            b_delta_y_charge_flash[0] = b_flash_y[best_true_idx] - b_charge_vtx_y[0]
            b_delta_z_charge_flash[0] = b_flash_z[best_true_idx] - b_charge_vtx_z[0]
        else:
            b_matched_flash_idx[0] = -1
            b_delta_y_charge_flash[0] = -999.0
            b_delta_z_charge_flash[0] = -999.0

        t_out.Fill()

        if (ev_idx + 1) % 5 == 0 or ev_idx == total_entries - 1:
            print(f"  Processed {ev_idx + 1}/{total_entries} events (Prompt Flash PE={max_true_pe:.1f}, True Flashes={true_nu_count})")

    f_out.Write()
    f_out.Close()
    f_in.Close()
    print(f"==> Successfully produced output ntuple: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDS Physics Reconstruction Analyzer")
    parser.add_argument("--infile", type=str, required=True, help="Input art-ROOT file")
    parser.add_argument("--outfile", type=str, default="pds_physics_ntuple.root", help="Output ROOT Ntuple file")
    parser.add_argument("--max_events", type=int, default=-1, help="Max events to process")
    parser.add_argument("--flash-label", type=str, default="opflash__Reco2",
                        help="OpFlash collection to read, e.g. opflashre__ReOpFlash")
    args = parser.parse_args()

    FLASH_BRANCH = "recob::OpFlashs_%s." % args.flash_label
    print("reading flashes from %s" % FLASH_BRANCH)

    run_analyzer(args.infile, args.outfile, args.max_events)
