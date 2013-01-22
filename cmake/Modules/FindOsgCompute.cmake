SET(OSG_COMPUTE_INCLUDE_PATHS
  "${CUDA_TOOLKIT_ROOT}/include")

FIND_LIBRARY(OSG_COMPUTE_LIBRARY
  NAMES osgCompute
  PATHS ${OSG_COMPUTE_LIBRARY_PATHS})

FIND_LIBRARY(OSG_CUDA_LIBRARY
  NAMES osgCuda
  PATHS ${OSG_COMPUTE_LIBRARY_PATHS})

FIND_LIBRARY(OSG_CUDA_INIT_LIBRARY
  NAMES osgCudaInit
  PATHS ${OSG_COMPUTE_LIBRARY_PATHS})

FIND_LIBRARY(OSG_CUDA_UTIL_LIBRARY
  NAMES osgCudaUtil
  PATHS ${OSG_COMPUTE_LIBRARY_PATHS})

FIND_LIBRARY(OSG_CUDA_STATS_LIBRARY
  NAMES osgCudaStats
  PATHS ${OSG_COMPUTE_LIBRARY_PATHS})

IF (OSG_COMPUTE_LIBRARY AND OSG_CUDA_LIBRARY AND OSG_CUDA_INIT_LIBRARY AND OSG_CUDA_UTIL_LIBRARY AND OSG_CUDA_STATS_LIBRARY)
  SET(OSG_COMPUTE_LIBRARIES ${OSG_COMPUTE_LIBRARY} ${OSG_CUDA_LIBRARY}
    ${OSG_CUDA_INIT_LIBRARY} ${OSG_CUDA_STATS_LIBRARY}
    ${OSG_CUDA_UTIL_LIBRARY})
  SET(OSG_COMPUTE_FOUND TRUE)
ELSE (OSG_COMPUTE_LIBRARY AND OSG_CUDA_LIBRARY AND OSG_CUDA_INIT_LIBRARY AND OSG_CUDA_UTIL_LIBRARY AND OSG_CUDA_STATS_LIBRARY)
  SET(OSG_COMPUTE_LIBRARIES "")
  SET(OSG_COMPUTE_FOUND FALSE)
ENDIF (OSG_COMPUTE_LIBRARY AND OSG_CUDA_LIBRARY AND OSG_CUDA_INIT_LIBRARY AND OSG_CUDA_UTIL_LIBRARY AND OSG_CUDA_STATS_LIBRARY)


