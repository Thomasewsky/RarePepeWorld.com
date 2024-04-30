# RarePepeWorld.com Notes

This is the code used to run a website that displays Pepe cards from the Counterparty network. In this 
document I attempt to outline steps required to make the site run.   However, though the site worked on my 
setup, different setups may require various tweaks or adaptations. Some basic administration skills and/or Python 
programming skills may be required to get the site running. Moreover, software libraries used in this project 
may change, and thus minor code tweaks may be necessary to make the code comply with the latest libraries.
I try to provide as much details and relevant links as possible for duplicating the setup.

## Run Environment

The site was run under the following:
* Python 3.10
* Flask framework. See https://flask.palletsprojects.com.
* Server: cloud hosted,  Ubuntu Server 22.04 

I have not tested in other enviroments, but they may still work. However, running in different environments will 
possibly require multiple changes to the code and environmental settings. These instructions will focus on Ubuntu 
22.04.

## Code Files

The following code paths/files are part of this repo:

`rpw/` → base path of python code

`run.sh[suffix], Settings.py[suffix]` -> sample run and settings scripts

> `_live` -> sample scripts for running a server hosted on an external domain 

> `_local` -> samples for running a local test server on localhost or 127.0.0.1

> `_ip` -> samples for running a local test server over an ip accessible externally 

`requirements.txt` → python pip packages to install for the site to be able to run.
Ideally,  installed in the python virtual environment of the running server. See
https://docs.python.org/3/tutorial/venv.html and below.

`rpw/static/` → Various unchanging files for the running site

`rpw/static/css` --> css style files

`rpw/static/data` --> various saved data: burn addresses, faq questions list, etc

`rpw/static/js` --> Javascript files

`rpw/static/sql` → Mysql database related files

`rpw/static/images`, `static/pepe_imagess`, `static/qr` → symbolic links to image files, pepe_images, qr. They 
were stored outside of repo, due to git provider storage limits and for sharing across run enviroments.

`rpw/static/sql/CounterpartyPepes.sql` → base sql database setup

`rpw/static/sql/CounterpartyPepes_Snapshot_[date].sql` -> snapshot of the sql data at a particular date. 
For quicker bootrapping of the site.

`rpw/templates/` → template files for determining the display of the website pages

`rpw/Logging.py` → Classes for directing log messages to various files/outputs

`rpw/QueryTools.py` → Classes for managing data pertaining to various elements of the site: XChain site, Counterparty node,
Pepe details from the database, price lookups, btcpayserver, etc

`rpw/PagesData.py` → Classes for prepping the data before it is passed to the Flask templates

`rpw/DataConnectors.py` → Lower level data access to the information sources: Mysql database queries, Xchain queries,
Counterparty rpc queries, btcpayserver queries

`rpw/Utils.py` → some tools for miscellaneous requirements: json file processing, qr code creation, pagination of lists

`rpw/app.py` → Flask entry point to the site. Determines how urls are rendered, triggers desired templates and components
required to display pages.

`sample_nginx_site.conf` -> Sample nginx configuration for a live site

`tools/` → various scripts for completing necessary tasks, like updating the database

`tools/db_updater.py` -> script for keeping the data of the site database updated

`tools/price_updater.py` -> script for maintaining the current prices in the database

## Flask Templates

The display of site pages determined by Flask templates in the `/templates/` folder. The python code passes the data to 
the template and are accessed as variables in the template file. How the templating system works can be found in this 
documentation: https://flask.palletsprojects.com/en/2.2.x/tutorial/templates/

## Site Run Instructions

The general steps for getting the site running are as follows:
* Clone this repo
* Setup python run environment
* Create/Edit the settings and run scripts
* Setup database details and populate it with the required information.
* Use the edited run script to launch the Python enviroment and the Flask server

### Clone the repo
Navigate to the location you wish to store the repo and run:

>  ``` git clone https://github.com/karlvance/RarePepeWorld.com.git ```

This will create the repo in the path RarePepeWorld.com/ where you ran the command.

### Setup a Python Run Environment

#### Ensure python has been installed on your system. 
For Ubuntu 22.04, the following packages can be installed for consistency with these instructions:

> ``` sudo apt install python3.10 python3.10-venv python3-pip python-is-python3 ```

Note: If *python-is-python3* in not installed in Ubuntu, you will have to specify python3 in all the scripts or explicitly 
call *python3* to use Python3.

#### Create the virtual environment for the site. 

Inside the repo path, run the following:
> ``` python -m pip install --user virtualenv ```

> ``` python -m venv .venv```

This creates the virtual environment files in the directory *.venv*. The name .venv is arbitrary, but what you 
choose needs to be specified in the run scripts.

For more information on Python virtual environments, 
see https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/

#### Activate the virtual environment:

Inside the repo path, run the following:

> ``` source .venv/bin/activate ```

Once the virtual environment is activated, install required packages via pip:

> ``` pip install -r requirements.txt```

### Edit the settings and run scripts
The repo provides various sample settings and run files for different contexts.  Copy the desired run.sh[suffix] and
Settings.py[suffix] file scripts.  These set the values used by the site launch and within the site presentation. Most
important will be to configure the database username and password.

> ``` cp Settings.py_local Settings.py ```

> ``` cp run.sh_local run.sh ```

NOTE: **Remember to change the database connection details in the Settings.py file before any execution, as failure to do so may result in errors.**

### Database setup

#### Install Mysql
To store the data for the site a Mysql database is needed.  For Ubuntu 22.04:

``` sudo apt install mysql-server ```

``` sudo systemctl enable --now mysql ```

See https://ubuntu.com/server/docs/databases-mysql for more details, or any of the many tutorials 
available for installing mysql on Ubuntu or other systems.  Make sure you have the root password for the database, 
which is different than the system root password.

#### Create a database user for the site:

Choose a username and password to be used by the site to access the database.  Load the settings file and navigate to
the section that starts with ```Sources = {```.  In the ```'mysql': {```, change the values at ```'user':``` and 
```'password': ``` to the values you will use for the database. Then update the Mysql database with the following:

> ``` sudo mysql -p```

> ``` mysql> CREATE USER 'cp'@'localhost' IDENTIFIED BY 'password';```

Replace *cp* and *password* with the chosen values.

#### Create the database tables. 

Either,
* Load the data from a snapshot.  A snapshots exists at rpw/static/sql/CounterpartyPepes_Snapshot_[date].sql for the particular 
*date* for which the snapshot was created:
> ``` sudo mysql -p ```
> ``` mysql> CREATE DATABASE CounterpartyPepes;```
> ``` mysql> EXIT; ```
> ``` sudo mysql -p CounterpartyPepes < CounterpartyPepes_Snapshot_20230418.sql ```

Enter the system user password, then the Mysql root password in the dialogs that follow.

or,
* if you do not have a snapshot, or wish to build the database from scratch, you can use the sql file
provided, then run the db population scripts later:

> ``` mysql -u 'root' -p < CounterpartyPepes.sql ``` 

For option 2, you will need to run the script that initiates all the data for the site:

> ``` cd tools/ ```

> ``` python db_updater.py initiate ```
 
#### Grant database user privileges

Enter the mysql console using the sytem password, then the Mysql root password:

> ``` sudo mysql -p ```

In the console, run the following:

> ``` mysql> USE CounterpartyPepes; ```

> ``` mysql> GRANT ALL PRIVILEGES ON CounterpartyPepes TO 'username'@'localhost'; ```

> ``` mysql> FLUSH PRIVILEGES;```

Replace *username* with the user defined in Settings.py.

### Keeping the data updated

#### Prices
> ``` cd tools/ ```
> 
> ``` python price_updater.py ```

#### Pepe data

> ``` cd tools/ ```
> 
> ``` python db_update full ```

There are various options:
* **full** - update the data for every pepe.  This can take an hour or more.
* **list pepe_name,pepe_name,...**  - update specific pepe data
* **start pepe_name** - start updating at pepe_name.  They are stored alphabetically
* **sync** - update only pepes for which there were changes since the last block after running _sync_, or _full_

You can run *full* once, then at a particular interval run *sync*.

### Pepe Images files

The images files required to run the site are not included in the repository. This is because github has file storage
limits and the Pepe images take over 1G of space.  Also, it keeps the repo much smaller. Moreover, it allows different
run environments to share the same image files. 

By default, there are three files in this repo that are symbolic links to the following paths:
> rpw/static/images -> /var/www/rpw/static/images

> rpw/static/pepe_images -> /var/www/rpw/static/pepe_images

> rpw/static/qr -> /var/www/rpw/static/qr 

These paths are arbitrary, but the files must be at the location where these symbolic links point.  To create them as
in the repo, you can do the following:

``` sudo mkdir -p /var/www/rpw/static/images/ /var/www/rpw/static/pepe_images/ /var/www/rpw/static/qr/ ```

Ensure the user that will run the site scripts has appropriate access to the files.  The user needs read permissions to 
*images* and *pepe_images*, and write permisions to *qr*:

> ``` sudo chmod 755 /var/www/rpw/static/images/ /var/www/rpw/static/pepe_images/ /var/www/rpw/static/qr/```

> ``` sudo chown -R username:username /var/www/rpw/static/qr/ ```

Download here: [Site Images](https://mega.nz/file/I7pnmZza#dhQy6fSE0gYq76f4eCGNSB3hikzrpxQ2D5LhC73zejg), 
[Pepe Images](https://mega.nz/file/B7xHmBgY#UayA0YzRgGJfCmDcgra0dd5-YXh9rg1ZTKjbroO-Zf4)

Copy the image files to the paths.  No files need to be added to the *qr* path; they will be created by the site.


> ``` tar xvfz PepeImages.tar.gz -C /var/www/rpw/static/ ```

> ``` tar xvfz SiteImages.tar.gz -C /var/www/rpw/static/ ```

### Local Run

To run local or connecting externally to your ip, the *run.sh_local* and run.sh_ip scripts gives an example command 
sequence.

By default, those scripts will :
* Activate the python environment
* Sets the appriate environmental variables
* launches the Flask server to the local network or via the ip address

Via these scripts, the site is accessed by navigating to http://localhost:55000, or http://ip-address:55000.

### Running on a Domain Name

To run via external domain, Nginx/Gunicorn can provide this functionality:

1. For description of this arrangment, see
  https://docs.gunicorn.org/en/stable/deploy.html,
  https://flask.palletsprojects.com/en/2.2.x/deploying/gunicorn/

* A sample nginx config file is provided, which can be tweeked as needed.  Also, you will likely
want to install a SSL certificate.  One option is to use a free certificate provided by
[Let's Encrypt](https://letsencrypt.org/).  For Ubuntu, a good way to install it is via
the package _certbot_. See https://snapcraft.io/install/certbot/ubuntu

2. The sample script for the live enviroment does the following:
  * changes to the path where the live site files are stored. Say, ```/var/www/rpw/run/RarePepeWorld/```
  * Sets some variables
  * Launches Gunicorn via ``` gunicorn -b 127.0.0.1:8000 "rpw.app:create_app()"```
      * gunicorn starts the Flask code that determines how the server responds to requests to the website
      * entry point is code file, `/var/www/rpw/run/RarePepeWorld/rpw/app.py`
      * gunicorn launches the `create_app()` method in ``` app.py ```

### Persistence: Byobu/Tmux/Pm2

* To keep the server running persistently and have it reload upon server reboot, some kind of service manager is 
needed. There are various options: systemd, byobu, tmux, etc.  Pm2 is a good choice.
* See https://byobu.org/, https://github.com/tmux/tmux, or https://pm2.io/.

## Resources

### Counterparty

Main site: https://counterparty.io/

Docs main: https://counterparty.io/docs/

Protocol specification: https://counterparty.io/docs/protocol_specification/

API: https://counterparty.io/docs/api/

### XChain

Main site: https://www.xchain.io/

API: https://www.xchain.io/api

### Pepes

RarePepe Directory: http://rarepepedirectory.com/

