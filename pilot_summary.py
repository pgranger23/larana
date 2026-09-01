#!/usr/bin/env python3
"""Per-event comparison of the prompt window before and after the larana patch.

Reads the slim output of pilot_reopflash.fcl, which carries the ORIGINAL production
flashes (opflash/Reco2, made with the buggy larana) and the RE-RUN flashes
(opflashre/ReOpFlash, made with the patched library) for the same events, plus the
generator truth. Writes one row per event.

Usage: pilot_summary.py <pilot_flashes.root> <out.root>
"""
import sys, array, ROOT

ROOT.gSystem.Load('libnusimdata_SimulationBase')
ROOT.gSystem.Load('liblardataobj_RecoBase')
ROOT.gErrorIgnoreLevel = ROOT.kError

OLD = 'recob::OpFlashs_opflash__Reco2.'
NEW = 'recob::OpFlashs_opflashre__ReOpFlash.'
GEN = 'simb::MCTruths_generator__GenieGen.'
WIN = 5.0


def product(tree, name):
    o = getattr(tree, name, None)
    if o is None:
        raise KeyError('missing branch: %s' % name)
    p = o.product()
    if p is None:
        raise KeyError('null product: %s' % name)
    return p


def main(infile, outfile):
    f = ROOT.TFile.Open(infile)
    t = f.Get("Events")
    fo = ROOT.TFile(outfile, "RECREATE")
    to = ROOT.TTree("pilot", "prompt window before/after the larana late-light fix")

    b = {n: array.array('f', [0.0]) for n in
         ("mc_nu_e", "mc_lepton_e", "pe_old", "pe_new")}
    bi = {n: array.array('i', [0]) for n in
          ("run", "subrun", "event", "is_cc", "nu_pdg", "n_old", "n_new",
           "nfl_old", "nfl_new")}
    for n, v in b.items():
        to.Branch(n, v, "%s/F" % n)
    for n, v in bi.items():
        to.Branch(n, v, "%s/I" % n)

    n_ev = 0
    n_diff = 0
    for i in range(t.GetEntries()):
        t.GetEntry(i)
        aux = t.EventAuxiliary
        bi["run"][0], bi["subrun"][0], bi["event"][0] = aux.run(), aux.subRun(), aux.event()

        old, new = product(t, OLD), product(t, NEW)
        bi["nfl_old"][0], bi["nfl_new"][0] = old.size(), new.size()
        for tag, coll in (("old", old), ("new", new)):
            pe = 0.0
            n = 0
            for fl in coll:
                if abs(fl.Time()) < WIN:
                    pe += fl.TotalPE()
                    n += 1
            b["pe_%s" % tag][0] = pe
            bi["n_%s" % tag][0] = n

        mct = product(t, GEN)
        if mct.size() and mct[0].NeutrinoSet():
            nu = mct[0].GetNeutrino()
            b["mc_nu_e"][0] = nu.Nu().E()
            b["mc_lepton_e"][0] = nu.Lepton().E()
            bi["nu_pdg"][0] = nu.Nu().PdgCode()
            bi["is_cc"][0] = 1 if nu.CCNC() == 0 else 0
        else:
            b["mc_nu_e"][0] = b["mc_lepton_e"][0] = -1.0
            bi["nu_pdg"][0] = bi["is_cc"][0] = -1

        if bi["nfl_new"][0] != bi["nfl_old"][0]:
            n_diff += 1
        to.Fill()
        n_ev += 1

    fo.cd(); to.Write(); fo.Close(); f.Close()
    print("pilot_summary: wrote %d events to %s" % (n_ev, outfile))

    # Self-check. If the patched library failed to load, opflashre would be produced by
    # the SAME algorithm as opflash and the two flash counts would agree on every event.
    # The patch deletes strictly fewer flashes, so it must differ on at least some.
    print("PATCH_CHECK: %d/%d events have nfl_new != nfl_old" % (n_diff, n_ev))
    if n_ev and n_diff == 0:
        print("PATCH_CHECK: FAILED - re-run is identical to production, "
              "the patched library did not load")
        sys.exit(3)
    print("PATCH_CHECK: OK")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
