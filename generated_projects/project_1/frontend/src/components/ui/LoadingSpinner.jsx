import React from 'react';

const LoadingSpinner = ({ className = "" }) => (
  <div className={`flex justify-center items-center ${className}`}>
    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600"></div>
  </div>
);

export default LoadingSpinner;