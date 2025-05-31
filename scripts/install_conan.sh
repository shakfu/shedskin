export CONAN_HOME=`pwd`/build/conan
mkdir -p  build
conan profile detect
conan install shedskin/resources/conan/conanfile2.txt --build=missing --output-folder=build/conan/scripts
mv build/conan/scripts/CMakePresets.json .

