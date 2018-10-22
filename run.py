import os
import sys
import subprocess
import time

def run_bot(autorestart):
    # From https://github.com/Cog-Creators/Red-DiscordBot/blob/develop/launcher.py
    interpreter = sys.executable

    if interpreter is None: # This should never happen
        raise RuntimeError('Couldn\'t find Python\'s interpreter')

    cmd = (interpreter, 'whalewolf.py')

    while True:
        try:
            code = subprocess.call(cmd)
        except KeyboardInterrupt:
            code = 2
            print('Received KeyboardInterrupt.')
            break
        else:
            if code == 0:
                break
            elif code == 16:
                print('Restarting...')
                continue
            else:
                if not autorestart:
                    break
        time.sleep(1)

    print(f'Bot has been terminated. Exit code: {code}')


if __name__ == '__main__':
    abspath = os.path.abspath(__file__)
    dirname = os.path.dirname(abspath)
    # Sets current directory to the script's
    os.chdir(dirname)
    run_bot(True)