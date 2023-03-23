#!/bin/bash
python3 -m pip install git-remote-codecommit
rm -rf $1
git clone codecommit::us-west-2://$1
cp -r realm_data $1
cd $1
git add . && git commit -m 'provision'
git push -f