import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight } from 'lucide-react';

const TodoPagination = ({ totalCount, pageSize }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentPage = parseInt(searchParams.get('page') || '1', 10);
  const totalPages = Math.ceil(totalCount / pageSize);

  if (totalPages <= 1) return null;

  const goToPage = (page) => {
    const newParams = new URLSearchParams(searchParams);
    if (page > 1) {
      newParams.set('page', page.toString());
    } else {
      newParams.delete('page');
    }
    setSearchParams(newParams);
  };

  return (
    <div className="flex items-center justify-center gap-4 mt-8 pb-8">
      <button
        onClick={() => goToPage(currentPage - 1)}
        disabled={currentPage === 1}
        className="p-2 rounded-full hover:bg-gray-200 disabled:opacity-30"
      >
        <ChevronLeft className="w-6 h-6" />
      </button>
      
      <div className="flex gap-2">
        {[...Array(totalPages)].map((_, i) => {
          const pageNum = i + 1;
          // Only show first, last, and neighbors of current page if many pages
          if (totalPages > 5 && (pageNum > 3 && pageNum < totalPages - 2 && Math.abs(pageNum - currentPage) > 1)) {
             if (pageNum === 4) return <span key={pageNum} className="px-2">...</span>;
             return null;
          }

          return (
            <button
              key={pageNum}
              onClick={() => goToPage(pageNum)}
              className={`w-10 h-10 rounded-md font-medium transition-colors ${
                currentPage === pageNum 
                  ? 'bg-blue-600 text-white' 
                  : 'hover:bg-gray-200 text-gray-600'
              }`}
            >
              {pageNum}
            </button>
          );
        })}
      </div>

      <button
        onClick={() => goToPage(currentPage + 1)}
        disabled={currentPage === totalPages}
        className="p-2 rounded-full hover:bg-gray-200 disabled:opacity-30"
      >
        <ChevronRight className="w-6 h-6" />
      </button>
    </div>
  );
};

export default TodoPagination;