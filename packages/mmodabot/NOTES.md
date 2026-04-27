Preparation:

- Make `docker-registry` type secret containing registry access credentials, e.g.
`kubectl create secret docker-registry SECRET_NAME --docker-server gitlab-registry.in2p3.fr --docker-username='TOKEN_NAME' --docker-password='TOKEN'`

  - If using gitlab registry:
    - `Role: Developer, scope: read_registry, write_registry` if builder enabled
    - `Role: Reporter, scope: read_registry` if builder disabled but some registries are private
    - May be ommited for public registries pull only
  - Tokens for several registries may be combined in a single secret, but not several tokens for same registry (e.g. different group tokens in the same gitlab)


- Create token to list group and access repos. `kubectl create secret generic SECRET_NAME --from-literal=token=TOKEN`
  - To list group, need at least `role: Reporter, scope: read_api`
  - Also enough for clonning repos (including private)
  - For setting commit status (notificator), needs `scope: api, read_api`, `role: Maintainer` 
    (the role depends on branch protection rules, Developer may be enought for unprotected branches).  
  - For separately defined public repos, still need at least `read_api` access for gitlab-interface to work
  - Need to define several and add names/keys to config

- Token may combine repo and registry access, but needs to be duplicated in two secrets anyway

- For repos with external resources (`oda:usesExternalResource`), precreate properly named and structured secrets. Ex. 

```bash
function depl_base_name() {
    repo_url=$1
    slug=$(echo ${repo_url/.git/} | awk -F'/' '{print $NF}')
    repo_id=$(uuidgen --sha1 -n @url -N ${repo_url} | awk -F'-' '{print $1}')
    echo "${slug}-${repo_id}"
}

kubectl create secret generic $(depl_base_name https://gitlab.in2p3.fr/mmoda/workflows/ligo-virgo-kagra.git)-gws3 --from-literal=credentials='{"endpoint": "minio.mmoda-minio-tenant", "secure": fal
se}'
```

