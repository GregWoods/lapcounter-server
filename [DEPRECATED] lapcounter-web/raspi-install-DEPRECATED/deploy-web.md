# Deploy Updated React Web App to the Pi

## On Dev Laptop

* Productionize the React app
```
npm run build

# uses webpack internally
# This creates/updates the local 'build' folder
```

* Commit and push using favourite git client. I use GitHub Desktop

* Update the code on the Pi

```
# ssh onto the Pi

cd ~/scalextric-lapcounter-react
git pull
mv /var/www/html /var/www/html-2023-12-xx-backup
cp -r ./build /var/www/html
```


# Alternative

And probably better approach, as no need for git and sourcecode on the pi...
And no need to commit the build folder
'scp' from Dev Laptop directly onto the Pi

