import argparse
import json
import os
import pathlib
import sys
import tempfile
from textwrap import dedent
from zipfile import ZipFile, ZIP_DEFLATED

PROJECT_JSON_NAME = 'project.json'
INNER_ZIP_NAME = 'scratch.sb3'

COMMON_HELP = dedent('''\
    Valid command are:
    
        dump_json
        copymyblocks <src> <dest>
    ''')

MISSING_COMMAND_HELP = 'You must provide a valid command. ' + COMMON_HELP
INVALID_COMMAND_HELP = 'You provided an invalid command. ' + COMMON_HELP


class ProjectFileFormatException(Exception):
    pass


def copy_all_except(inner_zip, inner_zip_out, name):
    for item in inner_zip.infolist():
        if item.filename != name:
            inner_zip_out.writestr(item, inner_zip.read(item.filename))


class ProjectFile:
    def __init__(self, project_file_name):
        self.project_file_name = project_file_name

    def get_project_json(self):
        with ZipFile(self.project_file_name) as project_zip:
            with project_zip.open(INNER_ZIP_NAME) as inner:
                with ZipFile(inner) as inner_zip:
                    with inner_zip.open(PROJECT_JSON_NAME) as project_json:
                        result = json.load(project_json)
        return result

    def update_project_code(self, project_code):
        # generate a temp file
        tmp_project_fd, tmp_project_name = tempfile.mkstemp(dir=os.path.dirname(self.project_file_name))
        tmp_inner_fd, tmp_inner_name = tempfile.mkstemp(dir=os.path.dirname(PROJECT_JSON_NAME))

        # this is poor practice as it potentially creates race conditions with attackers
        os.close(tmp_project_fd)
        os.close(tmp_inner_fd)

        # create a temp copy of the archive without filename
        with ZipFile(self.project_file_name) as project_zip:
            with project_zip.open(INNER_ZIP_NAME) as inner_file:
                with ZipFile(inner_file) as inner_zip:
                    with ZipFile(tmp_inner_name, 'w') as inner_zip_out:
                        inner_zip_out.comment = inner_zip.comment

                        # go through and copy all the context except the project.json
                        copy_all_except(inner_zip, inner_zip_out, PROJECT_JSON_NAME)

                    # write the json
                    with ZipFile(tmp_inner_name, mode='a', compression=ZIP_DEFLATED) as zf:
                        zf.writestr(PROJECT_JSON_NAME, project_code.as_json())

                    with ZipFile(tmp_project_name, 'w') as project_zip_out:
                        # go through and copy all the context except the project.json
                        copy_all_except(project_zip, project_zip_out, INNER_ZIP_NAME)

                    with ZipFile(tmp_project_name, 'a') as zf:
                        zf.write(tmp_inner_name, INNER_ZIP_NAME)

        os.unlink(tmp_inner_name)
        original_path = pathlib.Path(self.project_file_name)
        newfile_name = "new_" + original_path.name
        new_path = original_path.with_name(newfile_name)
        if new_path.exists():
            new_path.unlink()

        os.rename(tmp_project_name, new_path)


class ProjectCode:
    def __init__(self, project_file):
        self.code = project_file.get_project_json()

    def as_json(self):
        return json.dumps(self.code, indent=4)

    def get_blocks(self):
        non_stage_target = self.get_nonstage_target()

        if non_stage_target:
            return non_stage_target['blocks']

        raise ProjectFileFormatException("Unable to find blocks.")

    def get_nonstage_target(self):
        non_stage_target = None
        for target in self.code['targets']:
            if not target['isStage']:
                non_stage_target = target
        return non_stage_target

    def get_my_blocks(self):
        my_blocks = {}
        blocks = self.get_blocks()
        for key, block in blocks.items():
            if block['opcode'] == 'procedures_definition':
                my_block_parts = {}
                block_queue = set()
                block_queue.add(key)

                block_prototype = None
                while block_queue:
                    current_key = block_queue.pop()
                    current_block = blocks[current_key]

                    my_block_parts[current_key] = current_block

                    # print(current_block['opcode'])
                    if current_block['opcode'] == 'procedures_prototype':
                        block_prototype = current_block

                    referenced = set()
                    value_references(blocks.keys(), referenced, current_block)
                    # print("References", referenced)
                    # print("Processed", my_block_parts.keys())
                    unprocessed_references = referenced - my_block_parts.keys()
                    # print("Unprocessed to add", unprocessed_references)
                    block_queue |= unprocessed_references
                    # print("Live references:", block_queue)

                my_block_name = block_prototype['mutation']['proccode'].split()[0]
                my_blocks[my_block_name] = my_block_parts

        return my_blocks

    def copy_my_blocks_from(self, source):
        dest_blocks = self.get_blocks()
        src_my_blocks = source.get_my_blocks()
        dest_my_blocks = self.get_my_blocks()

        for src_my_block_name, src_my_blocks in src_my_blocks.items():
            # name conflict remove all the blocks in the destination project associated with the my block
            if src_my_block_name in dest_my_blocks:
                for dest_block_key in dest_my_blocks[src_my_block_name].keys():
                    del dest_blocks[dest_block_key]

            # copy in the blocks from the source
            for k, v in src_my_blocks.items():
                dest_blocks[k] = v

        non_stage_target = self.get_nonstage_target()

        if non_stage_target:
            non_stage_target['blocks'] = dest_blocks

        return dest_blocks


def value_references(target_set, collector, value):
    if isinstance(value, dict):
        for k, v in value.items():
            value_references(target_set, collector, v)
    elif isinstance(value, str):
        if value in target_set:
            collector.add(value)
        else:
            for v in value.split(','):
                if v in target_set:
                    collector.add(v)

    elif isinstance(value, list):
        for v in value:
            value_references(target_set, collector, v)


def dump_json_main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('project')
    opts = parser.parse_args(args)
    project_file = ProjectFile(opts.project)

    result = project_file.get_project_json()
    print(json.dumps(result, indent=4))
    print('-' * 80)

    code = ProjectCode(project_file)
    print(json.dumps(code.get_my_blocks(), indent=4))


def copy_my_blocks_main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('src_project')
    parser.add_argument('dest_project')
    opts = parser.parse_args(args)
    src_project_file = ProjectFile(opts.src_project)
    src_code = ProjectCode(src_project_file)
    dest_project_file = ProjectFile(opts.dest_project)
    dest_code = ProjectCode(dest_project_file)

    dest_code.copy_my_blocks_from(src_code)
    dest_project_file.update_project_code(dest_code)


if __name__ == '__main__':
    if not sys.argv:
        print(dedent(MISSING_COMMAND_HELP))
    else:
        command = sys.argv[1]
        remainder = sys.argv[2:]

        if command == 'dump_json':
            dump_json_main(remainder)
        elif command == 'copy_my_blocks':
            copy_my_blocks_main(remainder)
        else:
            print(dedent(INVALID_COMMAND_HELP))
