# psynet-adaptivetesting
An experiment that illustrates integration of [psynet](https://gitlab.com/PsyNetDev/PsyNet) with [adaptivetesting](https://github.com/condecon/adaptivetesting)



## Installing PsyNet and preparing to run this experiment

We highly recommend to run this under Linux and in a Python virtual environment using `venv`. This will spare you the hassle of setting up WSL2 and Docker under Windows. For final testing of your experiment before deploying it, we would recommend to run it in Docker once (again under Linux).

### Quick install instructions for Linux

Make sure you have a recent Python version (e.g., Python 3.12) and the Google Chrome browser installed.

Then get python dev packages, a database server and redis. E.g., for Ubuntu 22.04 LTS:

```sh
sudo apt install vim python3.11-dev python3.11-venv python3-pip redis-server git libenchant-2-2 postgresql postgresql-contrib libpq-dev unzip curl
```

For Ubuntu 24.04 LTS, just replace `python3.11-dev python3.11-venv` with `python3.12-dev python3.12-venv`.
For Ubuntu 20.03 LTS, just replace `python3.11-dev python3.11-venv` with `python3.9-dev python3.9-venv`.

Then setup the postgres database:

```sh
sudo service postgresql start
sudo -u postgres -i                  # opens a new shell as the database user 'postgres'
createuser -P dallinger --createdb   # add DB user dallinger with createDB permission. When asked for new password, enter 'dallinger' (twice).
createdb -O dallinger dallinger      # create database dallinger owned by user dallinger
createdb -O dallinger dallinger-import   # create database dallinger-import owned by user dallinger
exit                                     # exits the shell of user postgres, so you are back to your user
sudo service postgresql reload           # apply configuration
```

Install Heroku:

```sh
curl https://cli-assets.heroku.com/install-ubuntu.sh | sh
``

Now install the experiment from this repo, which will install dependencies like the PsyNet and Dallinger python packages:

```sh
git clone https://gitlab.gwdg.de/psynet_mpiae/psynet-ewmkids-robots.git
cd psynet-ewmkids-robots/
python -m venv venv
source venv/bin/activate
pip install -r constraints.txt    # This will get you PsyNet, Dallinger and their dependencies
psynet debug local                # starts PsyNet server and opens connection to it in your Chrome webbrowser.
```

Now we install extra dependencies of this experiment, which are not general psynet dependencies:

```sh
pip install adaptivetesting
```

For now, we need to hack Dallinger to allow large experiment directories. Note: Because of the legacy run command we use below to run our experiment, setting something like ```psynet.experiment.Experiment.max_exp_dir_size_in_mb = 2000``` in our derived `Experiment` class does not help, as with the legacy command, this is not passed on to the Dallinger launch functions used with legacy mode.

What you need to do is, find the Dallinger file `dallinger/command_line/utils.py` that is used by your PsyNet installation (Dallinger is a dpython dependency of PsyNet). If you followed the instructions above and your virtual environment is in the directory `venv`, it should be at `venv/lib/python3.11/site-packages/dallinger/command_line/utils.py`. If your used Python version is not `python3.11`, you will have to adapt the path accordingly, e.g., to `venv/lib/python3.12/site-packages/dallinger/command_line/utils.py`. There will only be one `python3.xy` directory in `venv/lib/`, just use that one.

In that file you found, you need to change ```def verify_directory(verbose=True, max_size_mb=50)``` to ```def verify_directory(verbose=True, max_size_mb=2000)```.

Now run our experiment:

```sh
psynet debug local --legacy
```

Note that the `--legacy` option ensures that Flask binds to all interfaces, in combination with the `host = 0.0.0.0` directive we have in the [config.txt](./config.txt) file in this directory. Without the legacy option, PsyNet will only listen on loopback (IP 127.0.0.1), but then we cannot connect with ipads to our local deployment server. All of this is only needed because we run PsyNet offline on a laptop in schools with no internet.



Chrome should open automatically and display the PsyNet overview page. If not, open Chrome manually and connect to [localhost:5000](http://localhost:5000).

Select the `Development` tab and click `New Participant` to run the experiment.

Note: If you are running an older Linux version and your system Python is very old, you can install [miniconda](https://www.anaconda.com/docs/getting-started/miniconda/install) and use it to get a more recent Python, or use uv.


### Other ways of installing

If you need to run this under Windows, please follow the full PsyNet installation instructions, available in [docs/INSTALL.md](./docs/INSTALL.md). In that case, you will also want to have a look at the list of run commands in [docs/RUN.md](./docs/RUN.md).

## General information on the PsyNet framework

For more information about PsyNet, see the [documentation website](https://psynetdev.gitlab.io/PsyNet/).


## Troubleshooting hints

#### Problem: I am being asked for credentials I don't know when manually connecting to the PsyNet overview page at http://localhost:5000.

Solution: PsyNet uses a user and password to protect its overview page and provides these credentials to Chrome automatically on startup. If you connect manually, you will be asked for this information. The easiest way to get the information is to define it yourself in the config file `~/.dallingerconfig` like this:

Create the file `~/.dallingerconfig` and put these lines into it (it's in INI format):

```
[Dashboard]
dashboard_user = admin
dashboard_password = 12345
```

Restart the PsyNet server. Then use these credentials to login when asked.


