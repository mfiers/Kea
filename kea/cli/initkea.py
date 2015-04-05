
import pkg_resources as pr

SCRIPT = """
if [[ ! "$PROMPT_COMMAND" =~ "_kea_prompt" ]];
then 
  export PROMPT_COMMAND="_kea_prompt;$PROMPT_COMMAND"; 
fi; 

function _kea_prompt { 
  local lc=$(history 1); 
  lc="${lc# *[0-9]*  }"; 
  export KEA_LAST_COMMAND=${lc}; 
}

"""

def dispatch():
    print(SCRIPT)
