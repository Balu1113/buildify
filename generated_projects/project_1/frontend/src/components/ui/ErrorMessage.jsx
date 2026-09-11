import React from 'react';
import { AlertCircle } from 'lucide-react';

const ErrorMessage = ({ message, className = "" }) => (
  <div className={`flex items-center p-4 mb-4 text-red-800 border-t-4 border-red-300 bg-red-50 ${className}`} role="alert">
    <AlertCircle className="flex-shrink-0 w-5 h-5" />
    <div className="ml-3 text-sm font-medium">{message}</div>
  </div>
);

export default ErrorMessage;