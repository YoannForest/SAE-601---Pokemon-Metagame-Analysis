# SAE-601---Pokemon-Metagame-Analysis

For the App launching, a PostgreSQL base is needed. 
It's possible to use a docker container to setup the base :
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_USER=postgres -v /absolute/path/to/data:/var/lib/postgresql/data postgres -c 'fsync=off'
 And after that, runnig the scrap_pokemon_postgresql.py will fill the database
The scrapping script is quite long ; there is a link to the filled database (PostGreSQL) https://filesender.renater.fr/?s=download&token=eb59e500-23a1-449d-9a81-1c245d5a4e56.
                                     Then, extract the pgsql.zip and launch the Start.bat

In order to setup the environnement, there is 2 options : - download and extract the already prepared environnement and run the RunApp.bat
                                                          -  type on a python terminal like Anaconda prompt
                                                          cd /d [the path where the app.py is located]
                                                          python -m venv env
                                                          And run the EnvSetup.bat which will install all the packages needed to run the App.

                                    
                                                        

                                                          - 
