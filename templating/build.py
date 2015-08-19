#!/usr/bin/env python
""" 
Batesian: A simple templating system using Jinja.

Architecture
============

                                                         INPUT FILE --------+
+-------+                           +----------+                            |
| units |-+                         | sections |-+                          V
+-------+ |-+ == used to create ==> +----------- | == provides vars to ==> Jinja
  +-------+ |                         +----------+                          |
   +--------+                                                               V
RAW DATA (e.g. json)                 Blobs of text                   OUTPUT FILE

Units
=====
Units are random bits of unprocessed data, e.g. schema JSON files. Anything can
be done to them, from processing it with Jinja to arbitrary python processing.
They are typically dicts.

Sections
========
Sections are strings, typically short segments of RST. They will be dropped in
to the provided input file based on their section key name (template var)
They typically use a combination of templates + units to construct bits of RST.

Input File
==========
The input file is a text file which is passed through Jinja along with the
section keys as template variables.

Processing
==========
- Execute all unit functions to load units into memory and process them.
- Execute all section functions (which can now be done because the units exist)
- Process the input file through Jinja, giving it the sections as template vars.
"""
from batesian import AccessKeyStore

from jinja2 import Environment, FileSystemLoader, StrictUndefined, Template
from argparse import ArgumentParser, FileType
import importlib
import json
import os
import sys
from textwrap import TextWrapper

def create_from_template(template, sections):
    return template.render(sections)

def check_unaccessed(name, store):
    unaccessed_keys = store.get_unaccessed_set()
    if len(unaccessed_keys) > 0:
        print "Found %s unused %s keys." % (len(unaccessed_keys), name)
        print unaccessed_keys

def main(input_module, file_stream=None, out_dir=None, verbose=False):
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)

    in_mod = importlib.import_module(input_module)

    # add a template filter to produce pretty pretty JSON
    def jsonify(input, indent=None, pre_whitespace=0):
        code = json.dumps(input, indent=indent, sort_keys=True)
        if pre_whitespace:
            code = code.replace("\n", ("\n" +" "*pre_whitespace))

        return code

    def indent_block(input, indent):
        return input.replace("\n", ("\n" + " "*indent))

    def indent(input, indent):
        return " "*indent + input

    def wrap(input, wrap=80, initial_indent=""):
        if len(input) == 0:
            return initial_indent
        wrapper = TextWrapper(initial_indent=initial_indent, width=wrap)
        return wrapper.fill(input)

    # make Jinja aware of the templates and filters
    env = Environment(
        loader=FileSystemLoader(in_mod.exports["templates"]),
        undefined=StrictUndefined
    )
    env.filters["jsonify"] = jsonify
    env.filters["indent"] = indent
    env.filters["indent_block"] = indent_block
    env.filters["wrap"] = wrap

    # load up and parse the lowest single units possible: we don't know or care
    # which spec section will use it, we just need it there in memory for when
    # they want it.
    units = AccessKeyStore(
        existing_data=in_mod.exports["units"](debug=verbose).get_units()
    )

    # use the units to create RST sections
    sections = in_mod.exports["sections"](env, units, debug=verbose).get_sections()

    # print out valid section keys if no file supplied
    if not file_stream:
        print "\nValid template variables:"
        for key in sections.keys():
            sec_text = "" if (len(sections[key]) > 75) else (
                "(Value: '%s')" % sections[key]
            )
            sec_info = "%s characters" % len(sections[key])
            if sections[key].count("\n") > 0:
                sec_info += ", %s lines" % sections[key].count("\n")
            print "  %s" % key
            print "      %s %s" % (sec_info, sec_text)
        return

    # check the input files and substitute in sections where required
    print "Parsing input template: %s" % file_stream.name
    temp = Template(file_stream.read())
    print "Creating output for: %s" % file_stream.name
    output = create_from_template(temp, sections)
    with open(
            os.path.join(out_dir, os.path.basename(file_stream.name)), "w"
            ) as f:
        f.write(output)
    print "Output file for: %s" % file_stream.name
    check_unaccessed("units", units)


if __name__ == '__main__':
    parser = ArgumentParser(
        "Processes a file (typically .rst) through Jinja to replace templated "+
        "areas with section information from the provided input module. For a "+
        "list of possible template variables, add --show-template-vars."
    )
    parser.add_argument(
        "file", nargs="?", type=FileType('r'),
        help="The input file to process. This will be passed through Jinja "+
        "then output under the same name to the output directory."
    )
    parser.add_argument(
        "--input", "-i", 
        help="The python module (not file) which contains the sections/units "+
        "classes. This module must have an 'exports' dict which has "+
        "{ 'units': UnitClass, 'sections': SectionClass, "+
        "'templates': 'template/dir' }"
    )
    parser.add_argument(
        "--out-directory", "-o", help="The directory to output the file to."+
        " Default: /out",
        default="out"
    )
    parser.add_argument(
        "--show-template-vars", "-s", action="store_true",
        help="Show a list of all possible variables (sections) you can use in"+
        " the input file."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Turn on verbose mode."
    )
    args = parser.parse_args()

    if not args.input:
        raise Exception("Missing [i]nput python module.")

    if (args.show_template_vars):
        main(args.input, verbose=args.verbose)
        sys.exit(0)

    if not args.file:
        print "No file supplied."
        parser.print_help()
        sys.exit(1)

    main(
        args.input, file_stream=args.file, out_dir=args.out_directory,
        verbose=args.verbose
    )