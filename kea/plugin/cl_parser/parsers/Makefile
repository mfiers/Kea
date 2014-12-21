
RULE_FILES := $(wildcard *.rules)
RULE2EBNF_FILES := $(RULE_FILES:.rules=.ebnf)

EBNF_FILES := $(wildcard *.ebnf)
EBNF2PY := $(EBNF_FILES:.ebnf=.py)

all: $(RULE2EBNF_FILES) $(EBNF2PY)


%.py: %.ebnf
	grako -w "" $< > $@

%.ebnf: %.rules ruleconverter
	./ruleconverter $< > $@
