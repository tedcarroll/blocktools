# blocktools

A quick and dirty set of utilities to support sharing code between EV3 Classroom projects.

# Usage

This is a simple python script:

    > python bt.py
    You must provide a valid command. Valid command are:

    dump_json <project file>
    copymyblocks <src> <dest>

The blocks are embedded in the lmsp file as json. To dump the json from the lmsp file:

    > python bt.py dump_json sample.lmsp
    <json output omitted>

This script can also copy "my blocks" from one project to another. The intent is that you can maintain a library project
full of reusable my blocks and copy them into other projects to reuse them.

    > python bt.py library.lmsp project.lmsp

After the above completes, all the my blocks from the library.lmsp project will be in the project.lmsp file. If any my
blocks in the library.lmsp file have the same name as a my block in project.lmsp, the my block in project.lmsp will be
overwritten. If this happens you may have to fix all the places where the replaced my block was used.