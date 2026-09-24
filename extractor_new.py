#!/usr/bin/env python
import sys, getopt
import os
from subprocess import Popen, PIPE
import threading
import queue
import json
import abc
import datetime

DEBUG=False

import argparse
  
from metacat.webapi import MetaCatClient

mc_client = MetaCatClient(os.getenv("METACAT_SERVER_URL"))


# Function to wait for a subprocess to finish and fetch return code,
# standard output, and standard error.
# Call this function like this:
#
# q = Queue.Queue()
# jobinfo = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
# wait_for_subprocess(jobinfo, q)
# rc = q.get()      # Return code.
# jobout = q.get()  # Standard output
# joberr = q.get()  # Standard error

"""extractor_new.py
Purpose: To extract metadata from output file on worker node, generate JSON file
"""


class MetaData(object):
    """Base class to hold / interpret general metadata"""
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def __init__(self, inputfile):
        self.inputfile = inputfile

    def extract_metadata_to_pipe(self):
        """Extract metadata from inputfile into a pipe for further processing."""
        local = self.inputfile
        if len(local) > 0:
            proc = Popen(["sam_metadata_dumper", local], stdout=PIPE,
                         stderr=PIPE)
        else:
            url = self.inputfile
            proc = Popen(["sam_metadata_dumper", url], stdout=PIPE,
                         stderr=PIPE)
        if len(local) > 0 and local != self.inputfile:
            os.remove(local)
        return proc
    
    def get_job(self, proc):
        """Run the proc in a 60-sec timeout queue, return stdout, stderr"""
        q = queue.Queue()
        thread = threading.Thread(target=self.wait_for_subprocess, args=[proc, q])
        thread.start()
        thread.join(timeout=7200)
        if thread.is_alive():
            print('Terminating subprocess because of timeout.')
            proc.terminate()
            thread.join()
        rc = q.get()
        jobout = q.get()
        joberr = q.get()
        if rc != 0:
            raise RuntimeError('sam_metadata_dumper returned nonzero exit status {}.'.format(rc))
        return jobout, joberr
    
    @staticmethod
    def wait_for_subprocess(jobinfo, q):
        """Run jobinfo, put the return code, stdout, and stderr into a queue"""
        jobout, joberr = jobinfo.communicate()
        rc = jobinfo.poll()
        for item in (rc, jobout, joberr):
            q.put(item)
        return

    @staticmethod

    def mdart_gen(jobtuple):
        """Take Jobout and Joberr (in jobtuple) and return mdart object from that"""
###        mdtext = ''.join(line.replace(", ,", ",") for line in jobtuple[0].split('\n') if line[-3:-1] != ' ,')
        mdtext = ''.join(line.replace(", ,", ",") for line in jobtuple[0].decode().split('\n') if line[-3:-1] != ' ,')
        mdtop = json.JSONDecoder().decode(mdtext)
        if len(list(mdtop.keys())) == 0:
            print('No top-level key in extracted metadata.')
            sys.exit(1)
        file_name = list(mdtop.keys())[0]
        return mdtop[file_name]

    @staticmethod
    def md_handle_application(md):
        """If there's no application key in md dict, create the key with a blank dictionary.
        Then return md['application'], along with mdval"""
        if 'application' not in md:
            md['application'] = {}
        return md['application']



class MetaDataKey:

    def __init__(self):
        self.expname = ''

    def metadataList(self):
        return [self.expname + elt for elt in ('lbneMCGenerators','lbneMCName','lbneMCDetectorType','StageName')]

    def translateKey(self, key):
        if key == 'lbneMCDetectorType':
            return 'lbne_MC.detector_type'
        elif key == 'StageName':
            return 'lbne_MC.miscellaneous'
        else:
            prefix = key[:4]
            stem = key[4:]
            projNoun = stem.split("MC")
            return prefix + "_MC." + projNoun[1]



class expMetaData(MetaData):
    """Class to hold/interpret experiment-specific metadata"""
    def __init__(self, expname, inputfile):
        MetaData.__init__(self, inputfile)
        self.expname = expname
        #self.exp_md_keyfile = expname + '_metadata_key'
#        try:
#            #translateMetaData = __import__("experiment_utilities", "MetaDataKey")
#            from experiment_utilities import MetaDataKey
#        except ImportError:
#            print("You have not defined an experiment-specific metadata and key-translating module in experiment_utilities. Exiting")
#            raise
#	    
        metaDataModule = MetaDataKey()
        self.metadataList, self.translateKeyf = metaDataModule.metadataList(), metaDataModule.translateKey

    def translateKey(self, key):
        """Returns the output of the imported translateKey function (as translateKeyf) called on key"""
        return self.translateKeyf(key)

    def md_gen(self, mdart, md0={}):
        """Loop through art metdata, generate metadata dictionary"""
        # define an empty python dictionary which will hold sam metadata.
        # Some fields can be copied directly from art metadata to sam metadata.
        # Other fields require conversion.
        md = {}
        topmd = {}
	
	# Loop over art metadata.
        if DEBUG: print ("EXTRACTOR: art",mdart.keys())
        for mdkey in list(mdart.keys()):
            mdval = mdart[mdkey]
		# Skip some art-specific fields.
            if mdkey == 'file_format_version':
                pass
            elif mdkey == 'file_format_era':
                pass

		# Ignore primary run_type field (if any).
		# Instead, get run_type from runs field.

            # #HMS  elif mdkey == 'run_type':
            # #     pass
            # elif mdkey == 'application.version':
            #     pass
            # elif mdkey == 'application.family':
            #     pass
            # elif mdkey == 'application.name':
            #     pass

		# do not Ignore data_stream any longer.

            elif mdkey == 'data_stream':
                if 'dunemeta.data_stream' not in list(mdart.keys()): # only use this data_stream value if dunemeta.data_stream is not present
                    md['core.data_stream'] = mdval

		# Ignore process_name as of 2018-09-22 because it is not in SAM yet
            elif mdkey == 'art.process_name':
#                md['core.application.name'] = mdval
                pass
		# Application family/name/version.

            elif mdkey == 'applicationFamily':
                md['core. application.family'] = mdval
            elif mdkey == 'StageName' or mdkey == 'applicationName':
                md['core.application.name'] = mdval
            elif mdkey == 'applicationVersion':              
                md['core.application.version'] = mdval
            
            # patch time format

            elif mdkey in ("start_time", "end_time"):
              
                newk = "core."+mdkey
                t = mdval
                if t is not None:
                    t = datetime.datetime.fromisoformat(t).replace(
                                tzinfo=datetime.timezone.utc).timestamp()
                    md[newk] = t
                    print ("EXTRACTOR: fix time for",mdval,newk,t,md[newk])

		# Parents.

            elif mdkey == 'parents':
                mdparents = []
                if not args.strip_parents:
                    for parent in mdval:
                        parent_dict = {'name': parent,'namespace':'unknown'}
                        mdparents.append(parent_dict)
                    topmd['parents'] = mdparents

		# Other fields where the key or value requires minor conversion.
            elif mdkey == 'runs':
                runsSubruns = []
                runs = []
                print (mdart['runs'])
                for run, subrun, runtype in mdart.pop("runs", []):
                    if run not in runs: runs.append(run)
                    if subrun not in runsSubruns: runsSubruns.append(100000 * run + subrun)
                md['core.runs'] = runs
                md['core.runs_subruns'] = runsSubruns
            
            elif mdkey == 'art.first_event':
                md[mdkey] = mdval[2]
            elif mdkey == 'art.last_event':
                md[mdkey] = mdval[2]
            elif mdkey == 'first_event':
                md['core.'+mdkey+ "_number"] = mdval  
            elif mdkey == 'last_event':
                md['core.'+mdkey+ "_number"] = mdval  
            elif mdkey == 'detector.hv_status':
                md[mdkey] = mdval
            elif mdkey == 'detector.hv_value':
                md[mdkey] = mdval
            elif mdkey == 'detector.tpc_status':
                md[mdkey] = mdval
            elif mdkey == 'detector.tpc_apa_status':
                md[mdkey] = mdval
            elif mdkey == 'detector.tpc_apas':
                md[mdkey] = mdval
            elif mdkey == 'detector.tpc_apa_1':
                md[mdkey] = mdval
            elif mdkey == 'detector.tpc_apa_2':
                md[mdkey] = mdval
            elif mdkey == 'detector.tpc_apa_3':
                md[mdkey] = mdval
            elif mdkey == 'detector.tpc_apa_4':
                md[mdkey] = mdval
            elif mdkey == 'detector.tpc_apa_5':
                md[mdkey] = mdval
            elif mdkey == 'detector.tpc_apa_6':
                md[mdkey] = mdval
            elif mdkey == 'detector.pd_status':
                md[mdkey] = mdval
            elif mdkey == 'detector.crt_status':
                md[mdkey] = mdval
            elif mdkey == 'daq.readout':
                md[mdkey] = mdval
            elif mdkey == 'daq.felix_status':
                md[mdkey] = mdval
            elif mdkey == 'beam.polarity':
                md[mdkey] = mdval
            elif mdkey == 'beam.momentum':
                md[mdkey] = mdval
            elif mdkey == 'dunemeta.data_stream':
                md['core.data_stream'] = mdval
            elif mdkey == 'file_type':
                md['core.'+mdkey] = mdval
            elif mdkey == 'data_quality.level':
                md[mdkey] = mdval
            elif mdkey == 'data_quality.is_junk':
                md[mdkey] = mdval
            elif mdkey == 'data_quality.do_not_process':
                md[mdkey] = mdval
            elif mdkey == 'data_quality.online_good_run_list':
                md[mdkey] = mdval
            elif mdkey == 'dunemeta.dune_data.accouple':
                md['dune_data.accouple'] = int(mdval)
            elif mdkey == 'dunemeta.dune_data.calibpulsemode':
                md['dune_data.calibpulsemode'] = int(mdval)
            elif mdkey == 'dunemeta.dune_data.daqconfigname':
                md['dune_data.DAQConfigName'] = mdval
            elif mdkey == 'dunemeta.dune_data.detector_config':
                md['dune_data.detector_config'] = mdval
            elif mdkey == 'dunemeta.dune_data.febaselinehigh':
                md['dune_data.febaselinehigh'] = int(mdval)
            elif mdkey ==  'dunemeta.dune_data.fegain':
                md['dune_data.fegain'] = int(mdval)
            elif mdkey == 'dunemeta.dune_data.feleak10x':
                md['dune_data.feleak10x'] = int(mdval)
            elif mdkey == 'dunemeta.dune_data.feleakhigh':
                md['dune_data.feleakhigh'] = int(mdval)
            elif mdkey == 'dunemeta.dune_data.feshapingtime':
                md['dune_data.feshapingtime'] = int(mdval)
            elif mdkey == 'dunemeta.dune_data.inconsistent_hw_config':
                md['dune_data.inconsistent_hw_config'] = int(mdval)
            elif mdkey == 'dunemeta.dune_data.is_fake_data':
                md['dune_data.is_fake_data'] = int(mdval)
            elif mdkey == 'dunemeta.dune_data.readout_window':
                md['dune_data.readout_window'] = float(mdval)
            
		# For all other keys, copy art metadata directly to sam metadata.
		# This works for run-tuple (run, subrun, runtype) and time stamps.

            else:
                if 'art' not in mdkey:
                    md['core.'+mdkey] = mdart[mdkey]
        
	# Make the other meta data field parameters				
        topmd['created_by'] = os.environ['USERF']
        topmd['name'] = self.inputfile.split("/")[-1]
        if 'file_size' in md0:
            topmd['size'] = md0['file_size']
        else:
            topmd['size'] = os.path.getsize(self.inputfile)
        # if 'crc' in md0 and not args.no_crc:
        #     topmd['crc'] = md0['crc']
        # elif not args.no_crc:
        #     topmdmd['crc'] = root_metadata.fileEnstoreChecksum(self.inputfile)

        # In case we ever want to check out what md is for any instance of MetaData by calling instance.md
        topmd['metadata'] = md
        self.topmd = topmd
        return self.topmd

    def getmetadata(self, md0={}):
        """ Get metadata from input file and return as python dictionary.
        Calls other methods in class and returns metadata dictionary"""
        proc = self.extract_metadata_to_pipe()
        jobt = self.get_job(proc)
        mdart = self.mdart_gen(jobt)
        return self.md_gen(mdart, md0)	

def main():

    argparser = argparse.ArgumentParser('Parse arguments')
    argparser.add_argument('--infile',help='path to input file',required=True,type=str)
    argparser.add_argument('--declare',help='validate and declare the metadata for the file specified in --infile to SAM',action='store_true')
    argparser.add_argument('--appname',help='application name for  metadata',type=str)
    argparser.add_argument('--appversion',help='application version for  metadata',type=str)
    argparser.add_argument('--appfamily',help='application family for  metadata',type=str)
    argparser.add_argument('--file_type',help='file_type (mc or detector)',type=str)
    argparser.add_argument('--file_format',help='file_format (root, artroot ..)',type=str)
    argparser.add_argument('--run_type',help='run_type - (fardet-hd, iceberg ...)',type=str)
    argparser.add_argument('--campaign',help='Value for dune.campaign for  metadata',type=str)
    argparser.add_argument('--data_stream',help='Value for data_stream for metadata',type=str)
    argparser.add_argument('--data_tier',help='Value for data_tier for metadata',type=str)
    argparser.add_argument('--fcl_file',type=str,help="fcl file name", default="unknown")
    argparser.add_argument('--requestid',help='Value for dune.requestid for  metadata',type=str)
    #argparser.add_argument('--set_processed',help='Set for parent file as processed in  metadata',action="store_true")
    argparser.add_argument('--strip_parents',help='Do not include the file\'s parents in  metadata for declaration',action="store_true")
    argparser.add_argument('--no_crc',help='Leave the crc out of the generated json',action="store_true")
    argparser.add_argument('--skip_dumper',help='Skip running sam_metadata_dumper on the input file',action="store_true")
    argparser.add_argument('--input_json',help='Input json file containing metadata to be added to output (can contain ANY valid metacat metadata parameters)',type=str)
    argparser.add_argument('--inputDidsFile', type=str, default=None, 
                      help='Optional path to a file containing all input DIDs, one per line')
    argparser.add_argument('--no_extract',help='use this if not artroot',action="store_true")
    argparser.add_argument('--namespace',type=str,help="namespace for output file",required=True)
    global args
    args = argparser.parse_args()

    try:
#        expSpecificMetadata = expMetaData(os.environ['SAM_EXPERIMENT'], str(sys.argv[1]))
        expSpecificMetadata = expMetaData('dune', args.infile)
        if not args.no_extract:
            mddict = expSpecificMetadata.getmetadata()
        else:
            mddict = {}
            mddict['name']=os.path.basename(args.infile)
            mddict['size'] = os.path.getsize(args.infile)
            mddict['created_by'] = os.environ['USERF']
            mddict['metadata']={}
            print ("EXTRACTOR: building metadata from parent and args as no artroot dump available")
        # If --input_json is supplied, open that dict now and add it to the output json
        if args.input_json != None:
            if os.path.exists(args.input_json):
                try:
                    arbjson = json.load(open(args.input_json,'r'))
                    if DEBUG: print ("EXTRACTOR: arbjson",arbjson)
                    
                    for key,newval in arbjson["metadata"].items():
                        
                        if key in mddict["metadata"]:
                            if DEBUG: print ("EXTRACTOR: overriding ",key,mddict["metadata"][key],"with", newval, "from json file" )
                        else:
                            if DEBUG: print ("EXTRACTOR: adding ",key, newval, "from json file" )

                        mddict["metadata"][key] = newval
                except:
                    print('Error loading input json file.',args.input_json)
                    
            else:
                print('warning, could not open the input json file', args.input_json)                

        if args.appname != None:
            mddict['metadata']['core.application.name'] = args.appname
        if  args.appversion != None:
            mddict['metadata']['core.application.version'] = args.appversion
        if args.appfamily != None:
            mddict['metadata']['core.application.family'] = args.appfamily
        if args.campaign != None:
            mddict['metadata']['dune.campaign'] = args.campaign
        if args.data_stream != None:
            mddict['metadata']['core.data_stream'] = args.data_stream
        if args.data_tier  != None:
            mddict['metadata']['core.data_tier'] = args.data_tier 
        if args.file_type != None:
            mddict['metadata']['core.file_type'] = args.file_type
        if args.file_format != None:
            mddict['metadata']['core.file_format'] = args.file_format
        if args.run_type != None:
            mddict['metadata']['core.run_type'] = args.run_type
        if args.requestid != None:
            mddict['metadata']['dune.requestid'] = args.requestid
        if args.inputDidsFile is not None:
            parentDids = []
            for line in open(args.inputDidsFile, "r").read().splitlines(): 
                ns = line.split(':')[0]
                name = line.split(':')[1]
                if DEBUG: print ("EXTRACTOR: found a parent",line)
                parentDids.append({ "name" : name, "namespace": ns }) 
            print ("EXTRACTOR: overriding parents with dids from " + args.inputDidsFile, file=sys.stdout)
            mddict["parents"] = parentDids

        if args.fcl_file is not None:
            mddict["metadata"]["dune.config_file"]=os.path.basename(args.fcl_file)

        mddict["metadata"]["retention.class"]="user"
        mddict["metadata"]["retention.status"]="active"
        mddict["metadata"]["core.file_content_status"]="good"
        # get info from the parent file if possible 
        # force some items to be like parents
        # and replace those that are missing from parents
            
        force = ['core.data_stream', 'core.run_type', 'core.file_type']
        inheritable = ['core.runs','core.runs_subruns']
        if 'parents' in mddict and len(mddict['parents']) > 0:
            theparent = mddict['parents'][0]
            thename = theparent['name']
            thenamespace = theparent['namespace']
            thedid = "%s:%s"%(thenamespace,thename)
            try:
                parentmd = mc_client.get_file(name=thename,namespace=thenamespace,with_metadata=True)
            except:
                print('Error retrieving parent metadata for did %s:%s' % (thenamespace,thename))
                parentmd = None
            if parentmd is not None:
                for key in force:  # these need to be the same as parents
                    if key in parentmd['metadata'] :
                        mddict['metadata'][key] = parentmd['metadata'][key]
                        print ("EXTRACTOR: forcing " + key + " from parent file " + thedid )
                for key in inheritable:
                    if key in parentmd['metadata'] and key not in mddict['metadata']:
                        mddict['metadata'][key] = parentmd['metadata'][key]
                        print ("EXTRACTOR: inheriting " + key + " from parent file " + thedid)
        print ("EXTRACTOR: setting namespace for output",args.namespace)
        mddict['namespace']=args.namespace




    except TypeError:
        print('You have not implemented a defineMetaData function by providing an experiment.')
        print('No metadata keys will be saved')
        raise
#    mdtext = json.dumps(expSpecificMetadata.getmetadata(), indent=2, sort_keys=True)
    
    if DEBUG: 
        mdtext = json.dumps(mddict, indent=2, sort_keys=True)
        print(mdtext)
    # if args.declare:
    #     ih.declareFile(mdtext)

    # if args.set_processed:
    #     swc = mc_client()
    #     moddict = {"DUNE.production_status" : "processed" }
    #     for parent in moddict['parents']:
    #         fname = moddict['parents'][parent]['file_name']
    #         try:
    #             swc.modifyFileMetadata(fname, moddict)
    #         except:
    #             print('Error modidying metadata for %s' % fname)
    #             raise
    of = open(mddict["name"]+".json",'w')
    json.dump(mddict,of,indent=4, sort_keys=True)
    of.close()
    #print(mdtext)
    sys.exit(0)



if __name__ == "__main__":
    main()


