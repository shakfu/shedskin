cmake_minimum_required(VERSION 3.5)

project(%(project_name)s LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)

# -----------------------------------------------------------------------------
# options

option(DEBUG "Enable debug output" OFF)

option(SIMPLE_PROJECT "Project has a single target and no subprojects" %(is_simple_project)s)

option(BUILD_EXECUTABLE "Build executable" ON)
option(BUILD_EXTENSION "Build python extension" OFF)
option(BUILD_TEST "Build test" ON)
option(DISABLE_EXECUTABLES "Disable building executables" OFF)
option(DISABLE_EXTENSIONS "Disable building extensions" OFF)
option(COLLECT_STATS "Collect stats" OFF)
option(ENABLE_SPM "Enable shedskin dependency management" OFF)
option(ENABLE_CONAN "Enable conan for dependency management" OFF)
option(ENABLE_EXTERNAL_PROJECT "Enable ExternalProject for dependency mgmt" OFF)

option(ENABLE_WARNINGS "Enable -Wall type of warnings" ON)

# -----------------------------------------------------------------------------
# reporting

message("Project: " ${PROJECT_NAME})
message("Build type: " ${CMAKE_BUILD_TYPE})
message("")

# -----------------------------------------------------------------------------
# warnings

if("${PROJECT_SOURCE_DIR}" STREQUAL "${PROJECT_BINARY_DIR}")
   message(FATAL_ERROR "In-source builds are not allowed.")
endif()

# -----------------------------------------------------------------------------
# find python executable and shedskin package path

find_package(Python REQUIRED COMPONENTS Interpreter Development)
if(DEBUG)
    message("python:" ${Python_EXECUTABLE})
    message("python_include:" ${Python_INCLUDE_DIRS})
endif()

# -----------------------------------------------------------------------------
# find shedskin package path

if(NOT DEFINED SHEDSKIN)
    execute_process(
        COMMAND ${Python_EXECUTABLE} -c "from shedskin import pkg_path; pkg_path()"
        OUTPUT_VARIABLE SHEDSKIN_PATH
        COMMAND_ERROR_IS_FATAL ANY
    )
    set(SHEDSKIN ${SHEDSKIN_PATH} CACHE PATH "setting path to shedskin pkg" FORCE)
endif()

set(SHEDSKIN_LIB ${SHEDSKIN}/lib)

include_directories(
    ${SHEDSKIN_LIB}
)

# -----------------------------------------------------------------------------
# dependency mgmt solutions

if(ENABLE_SPM)
    execute_process(
        COMMAND ${Python_EXECUTABLE} -c "from shedskin import cmake; cmake.user_cache_dir()"
        OUTPUT_VARIABLE SPM_DEPS
        COMMAND_ERROR_IS_FATAL ANY
    )
    message(STATUS "SPM_DEPS: ${SPM_DEPS}")
    set(SPM_LIB_DIRS ${SPM_DEPS}/lib)
    set(SPM_INCLUDE_DIRS ${SPM_DEPS}/include)

elseif(ENABLE_CONAN)
    find_program(CONAN conan)
    if(NOT CONAN)
        message(FATAL_ERROR "conan not found, install with `pip install conan`")
    endif()
    include(${CMAKE_BINARY_DIR}/conan_paths.cmake)
    find_package(BDWgc)
    find_package(PCRE)

elseif(ENABLE_EXTERNAL_PROJECT)
    set(install_dir ${CMAKE_CURRENT_BINARY_DIR}/install)
    include(ExternalProject)
    ExternalProject_Add(
        bdwgc
        INSTALL_DIR    ${install_dir}
        GIT_REPOSITORY https://github.com/ivmai/bdwgc.git
        GIT_TAG        d0ba209660ea8c663e06d9a68332ba5f42da54ba
        CMAKE_ARGS     -DCMAKE_INSTALL_PREFIX:PATH=${install_dir}
                       -DBUILD_SHARED_LIBS=OFF
                       -Denable_cplusplus=ON
    )
    ExternalProject_Add(
        pcre
        INSTALL_DIR    ${install_dir}
        URL            https://sourceforge.net/projects/pcre/files/pcre/8.45/pcre-8.45.tar.gz
        URL_MD5        01b80f8177ab91da63e7e5c5d5dfcb83
        CMAKE_ARGS     -DCMAKE_INSTALL_PREFIX:PATH=${install_dir}
    )
endif()


# -----------------------------------------------------------------------------
# includes
list(APPEND CMAKE_MODULE_PATH "${SHEDSKIN}/resources/cmake")
include(utils)
include(fn_add_shedskin_product)    # can build both executable and extension

# -----------------------------------------------------------------------
# any 'test_*' folders are automatically treated as tests

if(BUILD_TEST)
    enable_testing()
    if (EXISTS ${PROJECT_SOURCE_DIR}/testdata)
        # copy test data to cmake 'build' folder
        file(COPY ${PROJECT_SOURCE_DIR}/testdata DESTINATION ${CMAKE_CURRENT_BINARY_DIR})
    endif()

    # add_subdirectory(tests)
    file(GLOB test_dirs "test_*"
        LIST_DIRECTORIES true
    )

    foreach(testdir ${test_dirs})
        if(IS_DIRECTORY ${testdir})
            get_filename_component(testdir_name ${testdir} NAME_WLE)
            if (DEBUG)
                message("testdir_name:" ${testdir_name})
            endif()
            add_subdirectory(${testdir_name})
        endif()
    endforeach()
endif()


# -----------------------------------------------------------------------
# add subdirectories here
%(entry)s
