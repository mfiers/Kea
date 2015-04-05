#!/bin/bash
#
# This script is part of in the context of an
# installed kea version - in the case of a uninstalled version,
# as checked out from github, try ./util/keainit_u
#

#make sure we're being sourced
if [[ "$0" =~ "keainit" ]]; then
    echo "Please *source* this file, run:"
    echo "source {PATH/}keainit.sh"
    echo "(note the dot!!)"
    exit -1;
fi

if [[ ! "$PROMPT_COMMAND" =~ "_kea_prompt" ]]
then
    export PROMPT_COMMAND="_kea_prompt;$PROMPT_COMMAND"
fi

function _kea_prompt {

    #Get the last command
    #based on:
    #http://stackoverflow.com/questions/945288/...
    #     ...saving-current-directory-to-bash-history

    local lc=$(history 1)
    lc="${lc# *[0-9]*  }"

    export LAST_COMMAND=${lc}

    #make sure history is flushed
    history -a

    #if not in a kea dir - stop here
    [[ -d '.kea' ]] || return 0

    #and add the last history command to a local history
    if [[ -w '.kea' ]]
    then
        if [[ ! -a '.kea/local_bash_history' ]]
        then
            touch .kea/local_bash_history
        fi
        if [[ -w '.kea/local_bash_history' ]]
        then
            echo $lc >> .kea/local_bash_history 2>/dev/null || true
        fi
    fi
    if [[ "$KEA_PROMPT" ]]
    then
        #farm this out to a python script
        keaprompt
    fi
}
