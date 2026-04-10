FROM mambaorg/micromamba:2.5

RUN <<EOF
    micromamba create -n helper -c conda-forge python pyyaml git git-lfs 
    micromamba run -n helper git lfs install
EOF

# As kaniko is run with --single-snapshot, we don't optimize layers

ARG NB2W_VER
ARG REPO_URL
ARG GIT_REF
ARG COMMIT_ID

COPY <<EOF /home/mambauser/normalize-env.py
# This injects nb2workflow, git etc. into the environment spec
from glob import glob
import yaml
from copy import deepcopy
import sys
import os

def match_pkgspec(line: str, pkg=''):
    if (line.startswith(pkg) or
          (pkg in line and 
            (line.startswith('http') or line.startswith('git+'))
          )):
        return True
    return False

def inject_package(env_dict: dict, pkg: str, version_spec='', kind='pip', extras_spec=''):
    if kind not in ['pip', 'conda']:
        raise ValueError(f'Unknown package kind {kind} when injecting {pkg}')
    
    if version_spec.startswith('git+') or version_spec.startswith('http'):
        if kind == 'conda':
            raise ValueError(f"Conda package version spec can't be URL: {version_spec}")
        version_spec = f"@ {version_spec}"
    
    if extras_spec and kind=='conda':
        raise ValueError("Extras are not supported with conda")

    if 'dependencies' not in env_dict:
        env_dict['dependencies'] = []

    pipindx = None
    for ind, item in enumerate(deepcopy(env_dict['dependencies'])):
        if isinstance(item, str) and match_pkgspec(item, pkg):
            env_dict['dependencies'].pop(ind)
        elif isinstance(item, dict) and 'pip' in item.keys():
            pipindx = ind
            for pind, pitem in enumerate(item['pip']):
                if isinstance(pitem, str) and match_pkgspec(pitem, pkg):
                    env_dict['dependencies'][ind]['pip'].pop(pind)
    
    if kind == 'conda':
        env_dict['dependencies'].insert(0, pkg + version_spec)
    else:
        if version_spec:
            fullspec = f"{pkg}{extras_spec} {version_spec}"
        else:
            fullspec = f"{pkg}{extras_spec}"
        if pipindx is not None:
            env_dict['dependencies'][pipindx]['pip'].insert(0, fullspec)
        else:
            env_dict['dependencies'].append('pip')
            env_dict['dependencies'].append(
                {'pip': [fullspec]}
            )
    
    return env_dict

conda_env_file = glob('environment.y*ml')
req_txt_file = glob('requirements.txt')

dummy_env = {
    'name': 'base',
    'channels': ['conda-forge'],
    'dependencies': []
}

nb2wver = sys.argv[1] if len(sys.argv)==2 else ''

if len(conda_env_file) + len(req_txt_file) > 1:
    raise RuntimeError('Please define only one of requirements.txt or environment.yml')
elif req_txt_file:
    print("pip requirements")
    env_dict = dummy_env
    with open(req_txt_file[0]) as fd:
        for line in fd:
            if line.startswith('#'):
                continue
            env_dict = inject_package(env_dict, line.strip())
    os.remove(req_txt_file[0])
elif conda_env_file:
    print("Conda env")
    with open(conda_env_file[0]) as fd:
        env_dict = yaml.safe_load(fd)
    os.remove(conda_env_file[0])
else:
    print("Dummy env")
    env_dict = dummy_env
    
env_dict = inject_package(env_dict, 'nb2workflow', version_spec=nb2wver, extras_spec="[service]")
env_dict = inject_package(env_dict, 'git', kind='conda')
env_dict = inject_package(env_dict, 'git-lfs', kind='conda')

env_dict['name'] = 'base'

with open('environment.yml', 'w') as fd:
    yaml.dump(env_dict, fd)
EOF

COPY <<EOF /home/mambauser/config.py
# Configure entrypoint following mmoda.yaml, also write default kernelspec into ipynbs
import json
import os
import yaml
import logging
import sys
import glob 

logger = logging.getLogger()

repo_base = sys.argv[1]
cmd_path = sys.argv[2]

config = {
    "notebook_path": "",
    "filename_pattern": '.*'
}

if os.path.exists(os.path.join(repo_base, 'mmoda.yaml')):
    with open(os.path.join(repo_base, 'mmoda.yaml')) as fd:
        extra_config = yaml.safe_load(fd)
    config.update(extra_config)

nbpath = os.path.join(repo_base, config['notebook_path'].strip("/"))
filename_pattern = config['filename_pattern']
cmd = f"nb2service --debug --pattern '{ filename_pattern }' --host 0.0.0.0 --port 8000 { nbpath }"

with open(cmd_path, 'w') as fd:
    fd.write(cmd)

for fn in glob.glob(os.path.join(nbpath, r'*.ipynb')):
    with open(fn) as fd:
        nbjson = json.load(fd)
    nbjson['metadata']['kernelspec']['name'] = 'python3'
    with open(fn, 'w') as fd:
        json.dump(nbjson, fd)
EOF

# NOTE: this is ugly, but we need to clone here to have lfs objects. 
# Also, nb2workflow partially relies on workflow dir being a repo
# Otherwise, using git context directly in kaniko would be better
RUN --mount=type=secret,id=token,env=GIT_TOKEN <<EOF
    if [ "x$GIT_TOKEN" = "x" ]; then
        if [ "x$GIT_REF" = "x" ]; then
            micromamba -n helper run git clone --depth=1 ${REPO_URL} /home/mambauser/repo
        else
            micromamba -n helper run git clone --branch=${GIT_REF} --depth=1 ${REPO_URL} /home/mambauser/repo
        fi
        cd /home/mambauser/repo
    else
        if [ "x$GIT_REF" = "x" ]; then
            micromamba -n helper run git clone --depth=1 $( printf "%s" "$REPO_URL" | sed "s|https://|https://oauth2:$GIT_TOKEN@|") /home/mambauser/repo
        else
            micromamba -n helper run git clone --branch=${GIT_REF} --depth=1 $( printf "%s" "$REPO_URL" | sed "s|https://|https://oauth2:$GIT_TOKEN@|") /home/mambauser/repo
        fi
        cd /home/mambauser/repo
        micromamba -n helper run git remote set-url origin ${REPO_URL}
    fi
EOF

WORKDIR /home/mambauser/repo

# ensure no new commits appeared since job start
RUN <<EOF
    if [ "x${COMMIT_ID}" != "x" ] && [ "x$(micromamba -n helper run git rev-list -1 HEAD)" != "x$COMMIT_ID" ] ; then
        echo "Requested commit ${COMMIT_ID} is not the newest one."
        exit 1
        # git pull --unshallow
        # git checkout ${COMMIT_ID}
    fi
EOF

RUN micromamba run -n helper python /home/mambauser/normalize-env.py ${NB2W_VER}

RUN <<EOF
    micromamba install -y -n base -f /home/mambauser/repo/environment.yml
    micromamba env remove -n helper
    micromamba clean --all --yes
EOF

RUN micromamba run -n base python /home/mambauser/config.py /home/mambauser/repo /home/mambauser/cmd.sh ; chmod +x /home/mambauser/cmd.sh
RUN rm /home/mambauser/config.py /home/mambauser/normalize-env.py

RUN micromamba env config -n base vars set ODA_WORKFLOW_VERSION="$(micromamba run -n base git describe --always --tags)"
RUN micromamba env config -n base vars set ODA_WORKFLOW_LAST_AUTHOR="$(micromamba run -n base git log -1 --pretty=format:'%an <%ae>')"
RUN micromamba env config -n base vars set ODA_WORKFLOW_LAST_CHANGED="$(micromamba run -n base git log -1 --pretty=format:'%ai')"

CMD /home/mambauser/cmd.sh
