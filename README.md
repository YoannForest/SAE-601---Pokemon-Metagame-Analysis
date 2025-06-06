# SAE-601---Pokemon-Metagame-Analysis

<h2>For the App launching, a PostgreSQL base is needed </h2>

<p> It's possible to use a docker container to setup the base : </p>
<i>docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -v /absolute/path/to/data:/var/lib/postgresql/data postgres -c 'fsync=off' </i>
And after that, runnig the <i>scrap_pokemon_postgresql.py</i> will fill the database
The scrapping script is quite long ; there is a link to the filled database (PostGreSQL) <i>https://filesender.renater.fr/?s=download&token=eb59e500-23a1-449d-9a81-1c245d5a4e56</i>
                                     Then, extract the <i>pgsql.zip</i> and launch the <i>Start.bat</i>

In order to setup the environnement:
-  type on a python terminal like Anaconda prompt
 <i>cd /d [the path where the app.py is located]</i>
  <i>python -m venv env</i>
   And run the <i>EnvSetup.bat</i> which will install all the packages needed to run the App.

                                    
                                                        

                                                          - 
