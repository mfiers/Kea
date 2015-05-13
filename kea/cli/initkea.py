# initialize by adding:
#
# eval $(_init_kea)
#
# to your bashrc or your virtual environment activate script

SCRIPT = """
if [[ ! "$PROMPT_COMMAND" =~ "_kea_prompt" ]];
then export PROMPT_COMMAND="_kea_prompt;$PROMPT_COMMAND";
fi;

alias kea='#';

function _kea_prompt {
  local lc=$(history 1);
  export KEA_LAST_HIST=${lc};
  rex=' *[0-9]+ +kea';
  if [[ "$lc" =~ $rex ]]; then _kea; fi;
}

"""

def dispatch():
    print(SCRIPT)
